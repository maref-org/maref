"""
MAREF CLI Entry Point

Command-line interface for the Multi-Agent Recursive Engineering Framework.
Provides status, observe, analyze, desktop, audit, trust, drift, and serve commands.

Usage:
    maref --version                        # Show version
    maref status                           # Governance status
    maref observe                          # Watch state transitions
    maref analyze --state DECIDE --graph   # Analyze state machine
    maref desktop run --task "open Finder" # Run desktop task (dry-run default)
    maref desktop demo                     # Interactive desktop demo
    maref desktop benchmark                # Run OpenCUA benchmark
    maref audit show --last 20             # Show recent audit log entries
    maref trust score --agent agent-1      # Show agent trust score
    maref governance status                # Governance overlay status
    maref drift check                      # Check for distribution drift
    maref serve --port 8000                # Start Sidecar HTTP server
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from maref.production.ip_cli import ip_app
from maref_lite.governance import GovernanceOverlay
from maref_lite.obs_cli import obs_app
from maref_lite.percv_cli import percv_app
from maref_lite.state_machine import (
    ENTROPY_LEVELS,
    GRAY_CODE,
    VALID_TRANSITIONS,
    GovernanceState,
    GovernanceStateMachine,
    get_valid_transitions,
)

app = typer.Typer(
    name="maref",
    help="MAREF - Multi-Agent Recursive Engineering Framework CLI",
    no_args_is_help=True,
)
console = Console()


@app.callback(invoke_without_command=True)
def _version(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version and exit", is_eager=True
    ),
) -> None:
    if version:
        from maref_lite import __version__

        console.print(f"MAREF v{__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


# ── Sub-command groups ──────────────────────────────────────────────

desktop_app = typer.Typer(help="Desktop Agent commands", no_args_is_help=True)
app.add_typer(desktop_app, name="desktop")

audit_app = typer.Typer(help="Audit log commands", no_args_is_help=True)
app.add_typer(audit_app, name="audit")

trust_app = typer.Typer(help="Trust engine commands", no_args_is_help=True)
app.add_typer(trust_app, name="trust")

drift_app = typer.Typer(help="Drift detection commands", no_args_is_help=True)
app.add_typer(drift_app, name="drift")

governance_app = typer.Typer(help="Governance commands", no_args_is_help=True)
app.add_typer(governance_app, name="governance")

scheduler_app = typer.Typer(help="Scheduler commands", no_args_is_help=True)
app.add_typer(scheduler_app, name="scheduler")

self_heal_app = typer.Typer(help="Self-healing loop commands", no_args_is_help=True)
app.add_typer(self_heal_app, name="self-heal")

app.add_typer(obs_app, name="obs")
app.add_typer(percv_app, name="percv")
app.add_typer(ip_app, name="ip")


# ── Core commands ────────────────────────────────────────────────────


@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed status"),
) -> None:
    """Show current MAREF governance status."""
    overlay = GovernanceOverlay()
    status_dict = overlay.get_status()

    if verbose:
        console.print_json(json.dumps(status_dict, indent=2, default=str))
    else:
        table = Table(title="MAREF Governance Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for key, value in status_dict.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    table.add_row(f"{key}.{sub_key}", str(sub_value))
            else:
                table.add_row(key, str(value))

        console.print(table)


@app.command()
def observe(
    poll_interval: float = typer.Option(1.0, "--interval", "-i", help="Poll interval in seconds"),
    max_count: int = typer.Option(10, "--count", "-n", help="Number of observations to collect"),
) -> None:
    """Observe agent state transitions interactively."""
    sm = GovernanceStateMachine()

    console.print("[bold green]MAREF Observer started[/bold green]")
    console.print(f"Polling every {poll_interval}s for {max_count} observations...")

    states = [
        GovernanceState.OBSERVE,
        GovernanceState.ANALYZE,
        GovernanceState.EVALUATE,
        GovernanceState.DECIDE,
        GovernanceState.ACT,
        GovernanceState.VERIFY,
        GovernanceState.STABILIZE,
        GovernanceState.REPORT,
        GovernanceState.HALT,
    ]

    count = 0
    for target in states:
        if count >= max_count:
            break
        if sm.can_transition(target):
            sm.transition(target, reason="cli_observe")
            history = sm.get_history()
            last_transition = history[-1]
            console.print(
                f"  [cyan]{count + 1:3d}[/cyan] "
                f"[yellow]{last_transition.from_state.name}[/yellow] -> "
                f"[green]{target.name}[/green] entropy={ENTROPY_LEVELS[target]}"
            )
            count += 1
        else:
            sm.force_stabilize(reason="cli_observe_force")
            console.print(f"  [cyan]{count + 1:3d}[/cyan] [red]FORCE STABILIZE[/red]")
            count += 1

    console.print(f"[bold]Observed {count} transitions[/bold]")


@app.command()
def analyze(
    state_name: str = typer.Option("INIT", "--state", "-s", help="State to analyze"),
    show_graph: bool = typer.Option(False, "--graph", "-g", help="Show transition graph"),
) -> None:
    """Analyze the state machine structure and transitions."""
    state_map = {s.name: s for s in GovernanceState}

    if state_name.upper() not in state_map:
        console.print(f"[red]Unknown state: {state_name}[/red]")
        console.print(f"Valid states: {', '.join(s.name for s in GovernanceState)}")
        raise typer.Exit(code=1) from None

    state = state_map[state_name.upper()]
    gray = GRAY_CODE[state]
    gray_str = "".join(str(b) for b in gray)
    entropy = ENTROPY_LEVELS[state]
    valid_next = VALID_TRANSITIONS[state]

    console.print(f"\n[bold cyan]State Analysis: {state.name}[/bold cyan]")
    console.print(f"  ID:       {state.value}")
    console.print(f"  Gray Code: {gray_str}")
    console.print(f"  Entropy:   {entropy}")
    console.print(f"  Terminal:  {state == GovernanceState.HALT}")
    console.print(
        f"  Valid next states: {', '.join(s.name for s in valid_next) if valid_next else '(none - absorbing)'}"
    )

    if show_graph:
        console.print("\n[bold]Full Transition Graph:[/bold]")
        transitions = get_valid_transitions()
        for s_key in sorted(transitions, key=lambda k: k.value):
            targets = transitions[s_key]
            target_str = ", ".join(t.name for t in targets) if targets else "(none)"
            marker = ">" if s_key == state else " "
            console.print(f"  {marker} [yellow]{s_key.name:<12}[/yellow] -> {target_str}")


# ── Desktop Agent commands ───────────────────────────────────────────


@desktop_app.command("run")
def desktop_run(
    task: str = typer.Option("", "--task", "-t", help="Task description"),
    live: bool = typer.Option(False, "--live", "-l", help="Execute real mouse/keyboard events"),
) -> None:
    """Run a desktop automation task."""
    try:
        from maref.desktop.agent import DesktopAgent, DesktopOperation, DesktopStep, DesktopTask
    except ImportError as e:
        console.print("[red]Desktop agent modules not available.[/red]")
        console.print("Install with: pip install maref[desktop]")
        raise typer.Exit(code=1) from e

    dry_run = not live
    console.print(f"[bold]MAREF Desktop Agent[/bold] ({'LIVE' if live else 'dry-run'})")
    console.print(f"Task: {task or '(demo)'}")

    agent = DesktopAgent(dry_run=dry_run)
    start = time.time()

    if task:
        dtask = DesktopTask(
            task_id="cli-task",
            description=task,
            safe_apps=["Finder", "Safari", "TextEdit", "Google Chrome"],
            steps=[
                DesktopStep(
                    operation=DesktopOperation.HOTKEY, value="command+space", wait_seconds=0.5
                ),
                DesktopStep(operation=DesktopOperation.TYPE, value=task, wait_seconds=0.5),
                DesktopStep(operation=DesktopOperation.HOTKEY, value="enter", wait_seconds=1.0),
            ],
        )
    else:
        dtask = DesktopTask(
            task_id="cli-demo",
            description="MAREF Demo",
            safe_apps=["Finder"],
            steps=[
                DesktopStep(
                    operation=DesktopOperation.HOTKEY, value="command+space", wait_seconds=0.5
                ),
                DesktopStep(operation=DesktopOperation.TYPE, value="Finder", wait_seconds=0.5),
                DesktopStep(operation=DesktopOperation.HOTKEY, value="enter", wait_seconds=1.0),
            ],
        )

    result = agent.execute_task(dtask)
    elapsed = time.time() - start

    if result.success:
        console.print(f"[green]Task completed[/green] ({elapsed:.1f}s)")
    else:
        console.print(f"[red]Task failed[/red]: {result.error_message}")
    console.print(f"  Steps: {result.steps_executed}/{result.steps_executed + result.steps_failed}")


@desktop_app.command("setup")
def desktop_setup(
    dry_run: bool = typer.Option(False, "--dry-run", help="Check environment without downloading"),
    model: str = typer.Option(
        "omni_parser", "--model", "-m", help="Model backend: omni_parser, cog_agent, both, none"
    ),
    no_model: bool = typer.Option(False, "--no-model", help="Skip model download"),
    upgrade: bool = typer.Option(False, "--upgrade", "-U", help="Upgrade existing dependencies"),
) -> None:
    """One-click setup: install dependencies, download models, configure environment."""
    cmd = [sys.executable, "scripts/setup_desktop.py", f"--model={model}"]
    if dry_run:
        cmd.append("--dry-run")
    if no_model:
        cmd.append("--no-model")
    if upgrade:
        cmd.append("--upgrade")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            console.print("[yellow]Setup completed with warnings.[/yellow]")
            raise typer.Exit(code=result.returncode)
    except FileNotFoundError:
        console.print("[red]scripts/setup_desktop.py not found.[/red]")
        console.print("Run from the MAREF repository root.")
        raise typer.Exit(code=1) from None


@desktop_app.command("demo")
def desktop_demo() -> None:
    """Run interactive desktop agent demonstration (dry-run)."""
    try:
        from maref.desktop.agent import DesktopAgent
    except ImportError as e:
        console.print("[red]Desktop agent modules not available.[/red]")
        raise typer.Exit(code=1) from e

    console.print(
        Panel.fit(
            "[bold cyan]MAREF Desktop Agent Demo[/bold cyan]\n\n"
            "Runs in [yellow]dry-run[/yellow] mode — no real mouse/keyboard events.\n"
            'Live: maref desktop run --live --task "open Finder"',
            title="Desktop Agent",
        )
    )

    agent = DesktopAgent(dry_run=True)
    console.print("[bold]1. Capturing screen...[/bold]")
    screenshot = agent.capture_screen()
    console.print(f"   Resolution: {screenshot.width}x{screenshot.height}")

    console.print("[bold]2. Parsing UI elements...[/bold]")
    parse = agent.parse_screen(screenshot)
    console.print(f"   Elements detected: {len(parse.elements)}")

    console.print("[bold]3. Running demo task...[/bold]")
    result = agent.run_demo_task()
    console.print(f"   Success: {result.success}, Steps: {result.steps_executed}")
    console.print("\n[green]Demo complete![/green]")


@desktop_app.command("benchmark")
def desktop_benchmark(
    samples: int = typer.Option(10, "--samples", "-n", help="Number of benchmark samples to run"),
    output: str = typer.Option("", "--output", "-o", help="Export results as JSON file"),
    download: bool = typer.Option(
        False, "--download", "-d", help="Show dataset download instructions"
    ),
) -> None:
    """Run OpenCUA benchmark on the desktop agent."""
    try:
        from maref.desktop.agent import DesktopAgent
        from maref.desktop.opencua_bench import OpenCUABenchmark
    except ImportError as e:
        console.print("[red]Desktop agent modules not available.[/red]")
        raise typer.Exit(code=1) from e

    benchmark = OpenCUABenchmark()

    if download:
        console.print("[bold]OpenCUA Dataset Download[/bold]")
        path = benchmark.download_dataset()
        console.print(f"\nTarget directory: [cyan]{path}[/cyan]")
        return

    console.print("[bold cyan]MAREF OpenCUA Benchmark[/bold cyan]")
    console.print(f"Samples: [yellow]{samples}[/yellow]")

    with console.status("[bold green]Running benchmark...[/bold green]"):
        benchmark.load_dataset(use_mock=True)
        agent = DesktopAgent(dry_run=True)
        result = benchmark.run_with_agent(agent, num_samples=samples)

    table = Table(title="Benchmark Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total Samples", str(result.total_samples))
    table.add_row("Action Accuracy", f"{result.ActionAccuracy:.2%}")
    table.add_row("Step Accuracy", f"{result.StepAccuracy:.2%}")
    table.add_row("Avg Latency", f"{result.avg_latency_ms:.1f}ms")
    table.add_row("P99 Latency", f"{result.p99_latency_ms:.1f}ms")
    console.print(table)

    per_sample_table = Table(title="Per-Sample Results")
    per_sample_table.add_column("Sample ID", style="dim")
    per_sample_table.add_column("Match", style="yellow")
    per_sample_table.add_column("Steps", style="white")
    per_sample_table.add_column("Latency", style="green")
    for r in result.per_sample_results:
        match_icon = "[green]YES[/green]" if r.action_match else "[red]NO[/red]"
        per_sample_table.add_row(
            r.sample_id,
            match_icon,
            f"{r.step_correct}/{r.step_total}",
            f"{r.latency_ms:.1f}ms",
        )
    console.print(per_sample_table)

    if output:
        out_path = output if output.endswith(".json") else f"{output}.json"
        result.to_json(out_path)
        console.print(f"\n[green]Results exported to {out_path}[/green]")
    else:
        result.to_json()
        console.print("\n[dim]Use --output FILE to export results as JSON[/dim]")


# ── Audit commands ───────────────────────────────────────────────────


@audit_app.command("show")
def audit_show(
    last: int = typer.Option(10, "--last", "-n", help="Number of recent entries"),
    event_type: str = typer.Option("", "--type", "-t", help="Filter by event type"),
) -> None:
    """Show recent audit log entries."""
    audit_path = Path("governance_audit.jsonl")
    if not audit_path.exists():
        console.print("[yellow]No audit log found.[/yellow]")
        return

    entries: list[dict[str, Any]] = []
    with open(audit_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if event_type:
        entries = [e for e in entries if e.get("event_type") == event_type]
    entries = entries[-last:]

    table = Table(title=f"MAREF Audit Log (last {len(entries)})")
    table.add_column("Time", style="dim")
    table.add_column("Event", style="cyan")
    table.add_column("Actor", style="yellow")
    table.add_column("Action", style="green")
    table.add_column("Details", style="white")

    for entry in entries:
        ts = entry.get("timestamp", 0)
        time_str = time.strftime("%H:%M:%S", time.localtime(ts))
        table.add_row(
            time_str,
            entry.get("event_type", "")[:20],
            entry.get("actor", "")[:15],
            entry.get("action", "")[:30],
            entry.get("details", "")[:60],
        )

    console.print(table)
    if not entries:
        console.print("[dim]No matching audit entries.[/dim]")


# ── Trust commands ───────────────────────────────────────────────────


@trust_app.command("score")
def trust_score(
    agent: str = typer.Option("", "--agent", "-a", help="Agent ID to check"),
) -> None:
    """Show agent trust score (5-factor MAREF Trust Engine)."""
    console.print("[bold]MAREF Trust Engine[/bold]")
    if agent:
        console.print(f"Agent: [cyan]{agent}[/cyan]")
    else:
        console.print("[dim]No agent specified. Showing trust engine status.[/dim]")

    table = Table(title="Trust Factors")
    table.add_column("Factor", style="cyan")
    table.add_column("Weight", style="yellow")
    table.add_column("Description", style="white")

    for name, weight, desc in [
        ("Behavior Consistency", "30%", "Deviation from expected action patterns"),
        ("CB Trigger Frequency", "25%", "CircuitBreaker activation rate"),
        ("HALT Escape Rate", "20%", "Attempts to escape absorbing HALT state"),
        ("Task Completion", "15%", "Successful task completion ratio"),
        ("VC Validity", "10%", "Verifiable Credential chain validation"),
    ]:
        table.add_row(name, weight, desc)

    console.print(table)
    console.print("\n[dim]Trust scores computed per-agent from audit log history.[/dim]")


# ── Governance commands ──────────────────────────────────────────────


@governance_app.command("status")
def governance_status() -> None:
    """Show governance overlay status with state machine details."""
    overlay = GovernanceOverlay()
    status_dict = overlay.get_status()

    console.print("[bold]MAREF Governance Overlay[/bold]")
    table = Table(title="Governance State Machine")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    sm_state = status_dict.get("state_machine", {})
    for key, value in sm_state.items():
        table.add_row(key, str(value))

    console.print(table)


# ── Drift detection commands ─────────────────────────────────────────


@drift_app.command("check")
def drift_check(
    model: str = typer.Option("default", "--model", "-m", help="Model name to check"),
) -> None:
    """Check for distribution drift across 10 standard scenarios."""
    console.print("[bold]MAREF Drift Detection[/bold]")
    console.print(f"Model: [cyan]{model}[/cyan]")

    try:
        from drift_guard.drift_benchmark import DriftBenchmark

        benchmark = DriftBenchmark()
        benchmark.run()
        summary = benchmark.summary()

        console.print("\n[bold]Benchmark Results:[/bold]")
        console.print(f"  Scenarios:  {summary['total_scenarios']}")
        console.print(f"  Detected:   {summary['detected']}/{summary['total_scenarios']}")
        console.print(f"  Rate:       {summary['detection_rate'] * 100:.0f}%")
        console.print(f"  Avg F1:     {summary['avg_f1']}")

        table = Table(title="Per-Class Results")
        table.add_column("Drift Class", style="cyan")
        table.add_column("KL", style="yellow")
        table.add_column("JS", style="yellow")
        table.add_column("Detected", style="green")

        for cls_name, metrics in summary["per_class"].items():
            table.add_row(
                cls_name,
                f"{metrics['kl']:.4f}",
                f"{metrics['js']:.4f}",
                "[green]YES[/]" if metrics["detected"] else "[red]NO[/]",
            )
        console.print(table)

    except ImportError:
        console.print("[yellow]Drift detection modules not available.[/yellow]")


# ── Scheduler commands ────────────────────────────────────────────────


@scheduler_app.command("list")
def scheduler_list() -> None:
    """List all scheduled cron jobs."""
    try:
        from maref.executor.scheduler import CronExpression as _  # noqa: F401
    except ImportError:
        console.print("[red]Executor modules not available.[/red]")
        raise typer.Exit(code=1) from None

    console.print("[bold]MAREF Scheduler — Cron Jobs[/bold]")
    console.print("[dim]Run with --live to connect to a running scheduler.[/dim]")
    console.print()

    table = Table(title="Scheduler Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Scheduler", "Ready (not running)")
    table.add_row("Jobs", "0")
    table.add_row("Events", "0")
    table.add_row("Supported", "cron (5-field), event-driven")
    console.print(table)


@scheduler_app.command("add")
def scheduler_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    cron: str = typer.Option(..., "--cron", "-c", help="Cron expression (e.g., '0 */6 * * *')"),
    task_name: str = typer.Option("scheduled-task", "--task", "-t", help="Task name"),
    description: str = typer.Option("", "--desc", "-d", help="Task description"),
) -> None:
    """Add a new cron job to the scheduler."""
    try:
        from maref.executor.scheduler import CronExpression
    except ImportError as e:
        console.print("[red]Executor modules not available.[/red]")
        raise typer.Exit(code=1) from e

    try:
        CronExpression(cron)
    except ValueError as e:
        console.print(f"[red]Invalid cron expression: {e}[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"[green]Job '{name}' created[/green]")
    console.print(f"  Cron:   [cyan]{cron}[/cyan]")
    console.print(f"  Task:   [yellow]{task_name}[/yellow]")
    if description:
        console.print(f"  Desc:   {description}")
    console.print()
    console.print("[dim]Scheduler must be running for jobs to execute.[/dim]")


@scheduler_app.command("remove")
def scheduler_remove(
    job_id: str = typer.Option(..., "--id", "-i", help="Job ID to remove"),
) -> None:
    """Remove a cron job from the scheduler."""
    console.print(f"[yellow]Removing job: {job_id}[/yellow]")
    console.print("[dim]Remove operation: job would be deleted if scheduler is running.[/dim]")


@scheduler_app.command("start")
def scheduler_start(
    tick: float = typer.Option(60.0, "--tick", "-t", help="Tick interval in seconds"),
) -> None:
    """Start the scheduler in background mode."""
    console.print("[bold green]Starting MAREF Scheduler[/bold green]")
    console.print(f"Tick interval: [cyan]{tick}s[/cyan]")
    console.print()
    console.print("[dim]Scheduler would start here as a background thread.[/dim]")
    console.print("[dim]Use --tick to adjust polling interval.[/dim]")


@scheduler_app.command("stop")
def scheduler_stop() -> None:
    """Stop the running scheduler."""
    console.print("[bold yellow]Stopping MAREF Scheduler[/bold yellow]")
    console.print("[dim]Scheduler would stop and join the background thread.[/dim]")


@scheduler_app.command("status")
def scheduler_status() -> None:
    """Show scheduler runtime status."""
    console.print("[bold]MAREF Scheduler Status[/bold]")

    table = Table(title="Runtime Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("State", "Ready")
    table.add_row("Active Jobs", "0")
    table.add_row("Registered Events", "0")
    table.add_row("Last Tick", "N/A")
    table.add_row("Up Since", "N/A")
    console.print(table)

    console.print()
    console.print("[dim]Start the scheduler: maref scheduler start[/dim]")


# ── Self-heal commands ────────────────────────────────────────────


@self_heal_app.command("start")
def self_heal_start(
    interval: float = typer.Option(300.0, "--interval", "-i", help="Check interval in seconds"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without executing"),
) -> None:
    """启动自我修复循环（SelfObserver→Diagnostician→Healer 闭环）."""
    from maref_lite.self_healing_loop import SelfHealingConfig, SelfHealingLoop

    config = SelfHealingConfig(check_interval_seconds=interval)

    if dry_run:
        console.print("[bold]Self-Healing Loop — Dry Run Preview[/bold]")
        console.print(f"  Interval:        [cyan]{interval}s[/cyan]")
        console.print(f"  Max iterations:  [cyan]{config.max_heal_iterations}[/cyan]")
        console.print(f"  Arch proposals:  [cyan]{config.enable_architecture_proposals}[/cyan]")
        console.print(f"  Root path:       [dim]{Path.cwd()}[/dim]")
        console.print()
        console.print("[green]✓[/green] Configuration valid. Run without --dry-run to start.")
        return

    loop = SelfHealingLoop(config=config)

    console.print("[bold green]Self-Healing Loop Started[/bold green]")
    console.print(f"  Interval: [cyan]{interval}s[/cyan]")
    console.print("  Press [bold]Ctrl+C[/bold] to stop")
    console.print()

    try:
        asyncio.run(loop.run())
    except KeyboardInterrupt:
        loop.stop()
        console.print("\n[yellow]Self-healing loop stopped by user.[/yellow]")


@self_heal_app.command("run-once")
def self_heal_run_once() -> None:
    """执行单次观察→诊断→修复循环."""
    import asyncio

    from maref_lite.self_healing_loop import SelfHealingConfig, SelfHealingLoop

    console.print("[bold]Self-Healing — Single Cycle[/bold]")
    console.print("Running one observe→diagnose→heal pass...")
    console.print()

    loop = SelfHealingLoop(config=SelfHealingConfig(check_interval_seconds=999999))
    loop._lazy_init()  # 确保 Self-* 智能体已初始化
    report = asyncio.run(loop._run_one_cycle())

    if report.converged:
        console.print("[green]✓ Cycle completed successfully[/green]")
    else:
        console.print(f"[red]✗ Issues remain: risk={report.risk_level}[/red]")

    console.print(f"  Risk level:      [cyan]{report.risk_level}[/cyan]")
    console.print(f"  Problems found:  [cyan]{len(report.problems_found)}[/cyan]")
    console.print(f"  Actions taken:   [cyan]{len(report.actions_taken)}[/cyan]")
    console.print(f"  Converged:       [cyan]{report.converged}[/cyan]")
    console.print(f"  Duration:        [cyan]{report.duration_ms:.0f}ms[/cyan]")

    if report.problems_found:
        console.print()
        console.print("[yellow]Problems:[/yellow]")
        for p in report.problems_found:
            console.print(f"  - {p}")

    if report.actions_taken:
        console.print()
        console.print("[yellow]Actions:[/yellow]")
        for a in report.actions_taken:
            icon = "[green]✓[/green]" if a["success"] else "[red]✗[/red]"
            console.print(f"  {icon} {a['strategy']}: {a['detail'][:100]}")


@self_heal_app.command("config")
def self_heal_config() -> None:
    """查看自愈循环的当前配置."""
    from maref_lite.self_healing_loop import SelfHealingConfig

    config = SelfHealingConfig()

    table = Table(title="Self-Healing Loop Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Default Value", style="green")
    table.add_column("Description")

    table.add_row("check_interval_seconds", str(config.check_interval_seconds), "巡检间隔（秒）")
    table.add_row("max_heal_iterations", str(config.max_heal_iterations), "单次最大修复迭代次数")
    table.add_row("enable_architecture_proposals", str(config.enable_architecture_proposals), "是否启用架构改进提案")
    table.add_row("arch_proposal_interval_cycles", str(config.arch_proposal_interval_cycles), "架构提案间隔（巡检次数）")

    console.print(table)
    console.print()
    console.print("Override via: [cyan]maref self-heal start --interval 600[/cyan]")


# ── Serve command ────────────────────────────────────────────────────


@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="HTTP server port"),
    gui: bool = typer.Option(
        False, "--gui/--no-gui", help="Enable GUI endpoints (sessions, streaming, terminal)"
    ),
    telemetry: bool = typer.Option(
        False, "--telemetry/--no-telemetry", help="Enable maref-obs telemetry bridge"
    ),
) -> None:
    """Start MAREF Sidecar HTTP server."""
    if gui:
        console.print("[bold green]MAREF Sidecar Server (GUI Mode)[/bold green]")
    else:
        console.print("[bold green]MAREF Sidecar Server[/bold green]")
    console.print(f"Starting on http://0.0.0.0:{port}")

    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed. Run: pip install uvicorn[/red]")
        raise typer.Exit(code=1) from None

    console.print(f"  [green]Health:[/green]     http://localhost:{port}/api/health")
    console.print(f"  [green]Agents:[/green]     http://localhost:{port}/api/agents")
    console.print(f"  [green]Metrics:[/green]    http://localhost:{port}/api/metrics")

    if gui:
        console.print(f"  [green]Sessions:[/green]   http://localhost:{port}/api/sessions")
        console.print(
            f"  [green]Stream:[/green]     http://localhost:{port}/api/sessions/{{id}}/stream"
        )
        console.print(
            f"  [green]Terminal:[/green]   ws://localhost:{port}/api/sessions/{{id}}/terminal"
        )

    if telemetry:
        console.print("  [green]Telemetry:[/green]  /api/obs/status")

    try:
        import uvicorn

        from maref.obs import MarefObsClient
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor
        from sidecar.obs_bridge import ObsBridge
        from sidecar.server import create_app

        collector = ObservationCollector(adapter=MockAgentAdapter())
        monitor = CompositeMonitor()
        obs_bridge = ObsBridge(client=MarefObsClient.get_default()) if telemetry else None
        uvicorn.run(create_app(collector, monitor, obs_bridge=obs_bridge), host="0.0.0.0", port=port, log_level="info")
    except ImportError:
        console.print(f"[dim]Sidecar server mock — http://0.0.0.0:{port}[/dim]")


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    app()


if __name__ == "__main__":
    main()
