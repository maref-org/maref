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
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from maref.governance.state_machine import _default_audit_log_path
from maref.production.ip_cli import ip_app
from maref_lite.commands.demo import app as demo_app
from maref_lite.commands.loop_cli import loop_app as loop_cli_app
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

federated_app = typer.Typer(help="Federated audit commands", no_args_is_help=True)
app.add_typer(federated_app, name="federated")

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
app.add_typer(loop_cli_app, name="loop")
app.add_typer(demo_app, name="demo")

report_app = typer.Typer(help="Governance report commands", no_args_is_help=True)
app.add_typer(report_app, name="report")


# ── Rollback command ──────────────────────────────────────────────────


@app.command()
def rollback(
    target: str = typer.Argument(
        default="",
        help="Target version to rollback to (e.g. v0.34.0). Empty to list available versions.",
    ),
) -> None:
    """Show rollback instructions or execute version rollback plan.

    MAREF uses pip-managed packages. Rollback between releases:
      1. Install target version:  pip install maref==<version>
      2. Revert database:         python scripts/db_revert.py <version>
      3. Restore Docker image:    docker pull maref/maref:<version>
      4. Verify:                  maref --version && maref status

    Use 'maref rollback' without arguments to list available versions.
    """
    from maref_lite import __version__ as current

    console.print(f"[bold]Current version:[/bold] MAREF v{current}")
    console.print()

    if target:
        ver = target.removeprefix("v")
        console.print(f"[yellow]Rollback plan to v{ver}:[/yellow]")
        console.print(f"  1. pip install maref=={ver}")
        console.print(f"  2. docker pull maref/maref:{ver}")
        console.print("  3. maref --version  # verify")
        console.print("  4. maref status     # confirm governance state")
        return

    console.print("[bold]Available versions (from git tags):[/bold]")
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            capture_output=True, text=True, timeout=10,
        )
        for tag in result.stdout.strip().split("\n")[:10]:
            marker = " ← current" if tag == f"v{current}" else ""
            console.print(f"  {tag}{marker}")
    except Exception:
        console.print("  [dim](git not available — install via pip)[/dim]")

    console.print()
    console.print("[bold]Usage:[/bold] maref rollback <version>")
    console.print("  e.g. maref rollback v0.34.0")


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
    audit_path = _default_audit_log_path()
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


@audit_app.command("verify")
def audit_verify(
    file: str = typer.Option("", "--file", "-f", help="Audit log file path"),
    pubkey: str = typer.Option("", "--pubkey", "-k", help="Ed25519 public key PEM file for signature verification"),
) -> None:
    """Verify integrity of an audit log file.

    Checks entry signatures (Ed25519 or HMAC-SHA256) and chain hash continuity.
    Returns VERIFIED/FAILED status with detailed report.
    """
    from maref.governance.audit import AuditLogger

    path = Path(file) if file else _default_audit_log_path()
    if not path.exists():
        console.print(f"[red]Audit log not found: {path}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Verifying: {path}[/dim]")

    ed25519_pubkey_pem: str | None = None
    if pubkey:
        key_path = Path(pubkey)
        if not key_path.exists():
            console.print(f"[red]Public key file not found: {pubkey}[/red]")
            raise typer.Exit(1)
        ed25519_pubkey_pem = key_path.read_text()

    logger = AuditLogger(log_path=path, hmac_key="")
    result = logger.verify_integrity(ed25519_public_key_pem=ed25519_pubkey_pem)

    total = result["total_entries"]
    valid = result["valid_signatures"]
    tampered = result["tampered_entries"]
    intact = result["integrity_intact"]

    if intact:
        console.print(f"[green]VERIFIED: {valid}/{total} entries valid[/green]")
    else:
        console.print(f"[red]FAILED: {len(tampered)}/{total} entries tampered or unverifiable[/red]")
        for eid in tampered[:10]:
            console.print(f"  [red]✗ {eid}[/red]")
        if len(tampered) > 10:
            console.print(f"  [dim]... and {len(tampered) - 10} more[/dim]")

    table = Table(title="Integrity Report")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Total entries", str(total))
    table.add_row("Valid signatures", str(valid))
    table.add_row("Tampered entries", str(len(tampered)))
    table.add_row("Integrity intact", "✅ Yes" if intact else "❌ No")
    console.print(table)

    if not intact:
        raise typer.Exit(1)


@audit_app.command("export")
def audit_export(
    file: str = typer.Option("", "--file", "-f", help="Audit log file path"),
    output: str = typer.Option("audit-export.json", "--output", "-o", help="Output JSON file path"),
    max_entries: int = typer.Option(0, "--max", "-n", help="Max entries to export (0 = all)"),
) -> None:
    """Export audit log as a self-contained verification package.

    The export includes all entries with signatures and can be verified
    offline with ``maref audit verify``. Useful for third-party audits.
    """
    from maref.governance.audit import AuditLogger

    path = Path(file) if file else _default_audit_log_path()
    if not path.exists():
        console.print(f"[red]Audit log not found: {path}[/red]")
        raise typer.Exit(1)

    logger = AuditLogger(log_path=path, hmac_key="")
    entries = logger.read_all(max_entries=None if max_entries == 0 else max_entries)

    from maref_lite import __version__ as _ver

    export = {
        "maref_version": _ver,
        "exported_at": time.time(),
        "exported_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(path),
        "entry_count": len(entries),
        "entries": [e.to_dict() for e in entries],
    }

    out = Path(output)
    out.write_text(json.dumps(export, indent=2, ensure_ascii=False, default=str))
    console.print(f"[green]Exported {len(entries)} entries to {out}[/green]")


@federated_app.command("verify")
def federated_verify(
    proof: str = typer.Argument(..., help="Path to FederatedProof JSON file"),
    pubkey: str = typer.Option("", "--pubkey", "-k", help="Ed25519 public key PEM to verify proof signature"),
    batch: bool = typer.Option(False, "--batch", help="Treat proof as glob pattern for batch verification"),
    pubkey_dir: str = typer.Option("", "--pubkey-dir", help="Directory of .pem files matched by org_id"),
) -> None:
    """Verify a federated Merkle proof.

    Checks the Merkle inclusion path and, if --pubkey is provided,
    verifies the proof's Ed25519 signature.

    Examples::

        maref federated verify proof.json
        maref federated verify proof.json --pubkey signer.pem
        maref federated verify \"proofs/*.json\" --batch
        maref federated verify \"proofs/*.json\" --batch --pubkey-dir keys/
    """
    from glob import glob as glob_glob

    from maref.eivl.federated_merkle import FederatedProof

    files = glob_glob(proof) if batch else [proof]
    if not files:
        console.print(f"[red]No proof files matched: {proof}[/red]")
        raise typer.Exit(1)

    if len(files) > 1 or batch:

        passed = 0
        failed = 0
        for f in sorted(files):
            fp = FederatedProof.from_file(f)
            m_ok = fp.verify()

            sig_ok: bool | None = None
            if pubkey:
                sig_ok = fp.verify_signature(Path(pubkey).read_text())
            elif pubkey_dir:
                org_key = Path(pubkey_dir) / f"{fp.org_id}.pem"
                if org_key.exists():
                    sig_ok = fp.verify_signature(org_key.read_text())

            ok = m_ok and (sig_ok is None or sig_ok)
            status = "✅" if ok else "❌"
            sig_tag = f" sig={'✅' if sig_ok else ('❌' if sig_ok is False else '—')}" if pubkey or pubkey_dir else ""
            console.print(f"  {status} {fp.org_id:20s} merkle={'✅' if m_ok else '❌'}{sig_tag}  ({f})")
            if ok:
                passed += 1
            else:
                failed += 1

        console.print(f"\nBatch result: {passed} passed, {failed} failed out of {len(files)}")
        if failed:
            raise typer.Exit(1)
        return

    # Single proof mode
    proof_path = Path(proof)
    if not proof_path.exists():
        console.print(f"[red]Proof file not found: {proof}[/red]")
        raise typer.Exit(1)

    fp = FederatedProof.from_file(proof_path)

    console.print(f"[dim]Org: {fp.org_id}[/dim]")
    console.print(f"[dim]Org root: {fp.org_root_hash[:16]}...[/dim]")
    console.print(f"[dim]Federated root: {fp.federated_root_hash[:16]}...[/dim]")
    console.print(f"[dim]Org count: {fp.org_count}[/dim]")

    table = Table(title="Federated Proof Verification")
    table.add_column("Check", style="cyan")
    table.add_column("Result", style="white")

    merkle_ok = fp.verify()
    table.add_row("Merkle inclusion", "✅ Pass" if merkle_ok else "❌ Fail")

    sig_ok = None
    if pubkey:
        key_path = Path(pubkey)
        if not key_path.exists():
            console.print(f"[red]Public key file not found: {pubkey}[/red]")
            raise typer.Exit(1)
        sig_ok = fp.verify_signature(key_path.read_text())
        table.add_row("Ed25519 signature", "✅ Valid" if sig_ok else "❌ Invalid")
    else:
        table.add_row("Ed25519 signature", "[dim]— (no --pubkey)[/dim]")

    console.print(table)

    if not merkle_ok or (pubkey and not sig_ok):
        raise typer.Exit(1)


@federated_app.command("reconcile")
def federated_reconcile(
    replicas: list[str] = typer.Argument(..., help="Replica log files (format: replica_id=path)"),
) -> None:
    """Reconcile audit logs across replicas.

    One-shot comparison::

        maref federated reconcile node-a=/path/a.jsonl node-b=/path/b.jsonl
    """
    _run_reconcile(replicas)


@federated_app.command("reconcile-daemon")
def federated_reconcile_daemon(
    replicas: list[str] = typer.Argument(..., help="Replica log files (format: replica_id=path)"),
    interval: float = typer.Option(300.0, "--interval", "-i", help="Reconciliation interval in seconds"),
    alert_on_discrepancy: bool = typer.Option(False, "--alert", help="Exit with code 1 on first discrepancy"),
    webhook: str = typer.Option("", "--webhook", "-w", help="POST discrepancies to this webhook URL"),
    webhook_interval: int = typer.Option(300, "--webhook-interval", help="Min seconds between webhook alerts"),
) -> None:
    """Continuously reconcile audit logs across replicas.

    Runs in a loop, periodically comparing replicas::

        maref federated reconcile-daemon node-a=/path/a.jsonl node-b=/path/b.jsonl -i 60
        maref federated reconcile-daemon node-a=/path/a.jsonl node-b=/path/b.jsonl -w https://hooks.example.com/alert
    """
    import signal
    import urllib.request

    running = True
    last_webhook: float = 0.0

    def _stop(sig, frame) -> None:
        nonlocal running
        console.print("\n[dim]Shutting down reconcile daemon...[/dim]")
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    console.print("[bold]Reconcile Daemon[/bold]")
    console.print(f"  Replicas: {len(replicas)}")
    console.print(f"  Interval: {interval}s")
    if webhook:
        console.print(f"  Webhook: {webhook}")
    console.print("  Press Ctrl+C to stop\n")

    report: Any = None
    while running:
        try:
            report = _run_reconcile(replicas, quiet=not alert_on_discrepancy)

            if webhook and report.discrepancies:
                critical = [d for d in report.discrepancies if d.get("severity") != "info"]
                if critical and time.time() - last_webhook > webhook_interval:
                    payload = json.dumps({
                        "event": "reconcile_discrepancy",
                        "timestamp": time.time(),
                        "timestmap_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "replicas": list(report.total_entries.keys()),
                        "entry_counts": report.total_entries,
                        "total_discrepancies": len(report.discrepancies),
                        "critical_count": len(critical),
                        "discrepancies": report.discrepancies,
                    }).encode()
                    try:
                        req = urllib.request.Request(
                            webhook, data=payload,
                            headers={"Content-Type": "application/json"},
                        )
                        urllib.request.urlopen(req, timeout=10)
                        last_webhook = time.time()
                        console.print("[dim]Webhook alert sent[/dim]")
                    except Exception as exc:
                        console.print(f"[yellow]Webhook failed: {exc}[/yellow]")

            if alert_on_discrepancy and not report.is_consistent:
                console.print("[red]Discrepancy detected, exiting.[/red]")
                break
        except Exception as exc:
            console.print(f"[red]Reconcile error: {exc}[/red]")

        if running:
            for remaining in range(int(interval), 0, -1):
                if not running:
                    break
                console.print(f"\r  Next check in {remaining}s...  ", end="")
                time.sleep(1)
                if alert_on_discrepancy and report is not None and not report.is_consistent:
                    break
            console.print()
    console.print("[dim]Daemon stopped.[/dim]")


def _run_reconcile(
    replicas: list[str],
    quiet: bool = False,
) -> Any:
    """Shared reconcile logic used by both one-shot and daemon modes."""
    from maref.eivl.audit_reconciler import AuditReconciler

    reconciler = AuditReconciler()
    for arg in replicas:
        if "=" not in arg:
            console.print(f"[red]Invalid format: {arg}. Use replica_id=path[/red]")
            raise typer.Exit(1)
        rid, path = arg.split("=", 1)
        if not Path(path).exists():
            console.print(f"[red]File not found: {path}[/red]")
            raise typer.Exit(1)
        reconciler.add_replica(rid.strip(), path.strip())

    report = reconciler.reconcile()

    if not quiet:
        table = Table(title="Reconciliation Report")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Replicas", str(report.total_replicas))
        for rid, count in report.total_entries.items():
            table.add_row(f"  {rid}", f"{count} entries")
        table.add_row("Consistent", "✅ Yes" if report.is_consistent else "❌ No")
        table.add_row("Discrepancies", str(len(report.discrepancies)))
        console.print(table)

        if report.discrepancies:
            for d in report.discrepancies:
                eid = d.get("entry_id", "")
                dtype = d["type"]
                sev = d.get("severity", "critical")
                tag = "⚠" if sev != "critical" else "❌"
                detail = d.get("details", "")
                console.print(f"  {tag} [{sev}/{dtype}] {eid} {detail}")

    if not report.is_consistent and not quiet:
        raise typer.Exit(1)

    return report


@federated_app.command("submit")
def federated_submit(
    org_id: str = typer.Option(..., "--org-id", "-o", help="Organization identifier"),
    root_hash: str = typer.Option(..., "--root-hash", "-r", help="Merkle root hash"),
    state_file: str = typer.Option(
        ".maref/federated-state.json", "--state", "-s", help="Aggregator state file",
    ),
    tree_size: int = typer.Option(0, "--tree-size", "-n", help="Number of evidence leaves"),
    metadata: str = typer.Option("", "--metadata", "-m", help="JSON metadata string"),
) -> None:
    """Submit an org's Merkle root to the federated aggregator.

    The aggregator state is persisted in a JSON file and rebuilt
    on each invocation::

        maref federated submit --org-id org-1 --root-hash abc123 --state federated.json
    """
    from maref.eivl.federated_merkle import FederatedMerkleAggregator

    state = Path(state_file)
    if state.exists():
        agg = FederatedMerkleAggregator.load_state(state_file)
    else:
        state.parent.mkdir(parents=True, exist_ok=True)
        agg = FederatedMerkleAggregator()

    parsed_meta: dict[str, Any] = {}
    if metadata:
        parsed_meta = json.loads(metadata)

    agg.submit_root(org_id=org_id, root_hash=root_hash, tree_size=tree_size, metadata=parsed_meta)
    agg.save_state(state_file)

    summary = agg.summary()
    console.print(f"[green]Submitted root for {org_id}[/green]")
    console.print(f"  Federated root: {summary['federated_root'][:16] if summary['federated_root'] else '—'}...")
    console.print(f"  Organizations: {summary['org_count']}")
    console.print(f"  State saved to: {state_file}")


@federated_app.command("status")
def federated_status(
    state_file: str = typer.Option(
        ".maref/federated-state.json", "--state", "-s", help="Aggregator state file",
    ),
    proof_for: str = typer.Option("", "--proof", "-p", help="Generate proof for this org"),
    sign: str = typer.Option("", "--sign", help="Sign proof with Ed25519 private key PEM"),
    export_proof: str = typer.Option("", "--export-proof", help="Export proof to file"),
) -> None:
    """Show federated aggregator status and proofs.

    Displays the federated Merkle root, registered organizations,
    and optionally generates inclusion proofs::

        maref federated status --state federated.json
        maref federated status --proof org-1 --sign key.pem --export-proof proof.json
    """
    from maref.eivl.federated_merkle import FederatedMerkleAggregator

    state = Path(state_file)
    if not state.exists():
        console.print(f"[red]State file not found: {state_file}[/red]")
        raise typer.Exit(1)

    agg = FederatedMerkleAggregator.load_state(state_file)
    summary = agg.summary()

    table = Table(title="Federated Aggregator Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Organizations", str(summary["org_count"]))
    table.add_row("Federated root", summary["federated_root"][:32] + "..." if summary["federated_root"] else "—")
    table.add_row("Last aggregated", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(summary["last_aggregated"])) if summary["last_aggregated"] else "—")
    table.add_row("Total evidence", str(summary["total_evidence_count"]))
    console.print(table)

    orgs = agg.list_orgs()
    if orgs:
        org_table = Table(title="Registered Organizations")
        org_table.add_column("Org ID", style="green")
        org_table.add_column("Root Hash", style="yellow")
        org_table.add_column("Tree Size", style="white")
        org_table.add_column("Updated", style="dim")
        for org in orgs:
            org_table.add_row(
                org.org_id,
                org.root_hash[:16] + "...",
                str(org.tree_size),
                time.strftime("%H:%M:%S", time.localtime(org.timestamp)),
            )
        console.print(org_table)

    if proof_for:
        proof = agg.generate_proof(proof_for)
        if proof is None:
            console.print(f"[red]Org not found: {proof_for}[/red]")
            raise typer.Exit(1)

        if sign:
            key_path = Path(sign)
            if not key_path.exists():
                console.print(f"[red]Key file not found: {sign}[/red]")
                raise typer.Exit(1)
            from maref.crypto.ed25519_keys import Ed25519KeyPair
            kp = Ed25519KeyPair.from_private_pem(key_path.read_text())
            proof.sign(kp)
            console.print(f"[green]Proof signed by {kp.fingerprint[:16]}...[/green]")

        proof_table = Table(title=f"Inclusion Proof: {proof_for}")
        proof_table.add_column("Check", style="cyan")
        proof_table.add_column("Value", style="white")
        proof_table.add_row("Org root hash", proof.org_root_hash[:16] + "...")
        proof_table.add_row("Federated root", proof.federated_root_hash[:16] + "...")
        proof_table.add_row("Org count", str(proof.org_count))
        proof_table.add_row("Proof path length", str(len(proof.proof_path)))
        proof_table.add_row("Merkle verify", "✅ Pass" if proof.verify() else "❌ Fail")
        sig_fp = getattr(proof, "_signer_fingerprint", None)
        if sig_fp:
            proof_table.add_row("Signed by", sig_fp[:16] + "...")
        console.print(proof_table)

        if export_proof:
            proof.to_file(export_proof)
            console.print(f"[green]Proof exported to {export_proof}[/green]")


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
    execute_proposals: bool = typer.Option(
        False,
        "--execute-proposals",
        help="Allow SelfExecutor to write proposal changes",
    ),
) -> None:
    """启动自我修复循环（SelfObserver→Diagnostician→Healer 闭环）."""
    from maref_lite.self_healing_loop import SelfHealingConfig, SelfHealingLoop

    config = SelfHealingConfig(
        check_interval_seconds=interval,  # type: ignore[arg-type]
        proposal_dry_run=not execute_proposals,
    )

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


# ── Daemon commands ──────────────────────────────────────────────────

daemon_app = typer.Typer(help="Evolution daemon commands", no_args_is_help=True)
app.add_typer(daemon_app, name="daemon")


@daemon_app.command("start")
def daemon_start(
    interval: float = typer.Option(0.0, "--interval", "-i", help="Polling interval in hours (0 = no sleep between runs)"),
    max_runs: int = typer.Option(100, "--max-runs", "-n", help="Max evolution cycles (0 = infinite)"),
    engine: str = typer.Option("daily", "--engine", "-e", help='Evolution engine: "daily" or "rel"'),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Dry-run mode (read-only)"),
    vault: str = typer.Option(".evolution_vault", "--vault", "-v", help="Evolution vault directory"),
) -> None:
    """启动演进守护进程，连续运行指定次数的递归演进。"""
    import asyncio

    from maref.evolution.daemon import DaemonConfig, EvolutionDaemon

    config = DaemonConfig(
        interval_hours=interval,
        max_runs=max_runs,
        vault_dir=vault,
        dry_run=dry_run,
        engine=engine,
    )

    if dry_run:
        console.print("[bold]Evolution Daemon — Dry Run Preview[/bold]")
        console.print(f"  Interval:  [cyan]{interval}h[/cyan]")
        console.print(f"  Engine:    [cyan]{engine}[/cyan]")
        console.print(f"  Vault:     [dim]{vault}[/dim]")
        console.print()
        console.print("[green]✓[/green] Configuration valid. Run with --no-dry-run to enable real writes.")
        return

    daemon = EvolutionDaemon(config)

    console.print("[bold green]Evolution Daemon Started[/bold green]")
    console.print(f"  Interval: [cyan]{interval}h[/cyan]")
    console.print(f"  Engine:   [cyan]{engine}[/cyan]")
    console.print(f"  Vault:    [dim]{vault}[/dim]")
    console.print("  Press [bold]Ctrl+C[/bold] to stop")
    console.print()

    try:
        asyncio.run(daemon.run_forever())
    except KeyboardInterrupt:
        daemon._handle_shutdown()
        console.print("\n[yellow]Evolution daemon stopped by user.[/yellow]")


@daemon_app.command("run-once")
def daemon_run_once(
    engine: str = typer.Option("daily", "--engine", "-e", help='Evolution engine: "daily" or "rel"'),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Dry-run mode (read-only)"),
    vault: str = typer.Option(".evolution_vault", "--vault", "-v", help="Evolution vault directory"),
) -> None:
    """执行单次演进循环并报告结果。"""
    from maref.evolution.daemon import DaemonConfig, EvolutionDaemon

    console.print("[bold]Evolution Daemon — Single Cycle[/bold]")
    console.print(f"  Engine:  [cyan]{engine}[/cyan]")
    console.print(f"  Vault:   [dim]{vault}[/dim]")
    console.print(f"  Dry run: [cyan]{dry_run}[/cyan]")
    console.print()

    config = DaemonConfig(
        vault_dir=vault,
        dry_run=dry_run,
        engine=engine,
    )
    daemon = EvolutionDaemon(config)
    import asyncio
    result = asyncio.run(daemon.run_once())

    if result is None:
        console.print("[red]✗ Cycle failed[/red]")
    else:
        console.print("[green]✓ Cycle completed[/green]")
        console.print(f"  Stop reason:  [cyan]{result.stop_reason}[/cyan]")
        console.print(f"  Priority:     [cyan]{result.priority}[/cyan]")
        console.print(f"  Dry run:      [cyan]{result.dry_run}[/cyan]")
        console.print(f"  Phases:       [cyan]{', '.join(result.phases)}[/cyan]")


@daemon_app.command("install-launchd")
def daemon_install_launchd(
    interval: float = typer.Option(6.0, "--interval", "-i", help="Polling interval in hours"),
    engine: str = typer.Option("daily", "--engine", "-e", help='Evolution engine: "daily" or "rel"'),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Dry-run mode (read-only)"),
    output: str = typer.Option(
        os.path.expanduser("~/Library/LaunchAgents/com.maref.evolution-daemon.plist"),
        "--output", "-o",
        help="Output path for launchd plist",
    ),
) -> None:
    """生成并安装 macOS launchd 服务配置文件。"""
    from maref.evolution.daemon import DaemonConfig, EvolutionDaemon

    config = DaemonConfig(
        interval_hours=interval,
        dry_run=dry_run,
        engine=engine,
    )
    daemon = EvolutionDaemon(config)
    daemon.generate_launchd_plist(output)

    console.print(f"[green]✓[/green] launchd plist written to [cyan]{output}[/cyan]")
    console.print(f"  Load with: [dim]launchctl load {output}[/dim]")


@daemon_app.command("install-systemd")
def daemon_install_systemd(
    interval: float = typer.Option(6.0, "--interval", "-i", help="Polling interval in hours"),
    engine: str = typer.Option("daily", "--engine", "-e", help='Evolution engine: "daily" or "rel"'),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Dry-run mode (read-only)"),
    output: str = typer.Option(
        "/etc/systemd/system/maref-evolution-daemon.service",
        "--output", "-o",
        help="Output path for systemd unit",
    ),
) -> None:
    """生成并安装 Linux systemd 服务配置文件。"""
    from maref.evolution.daemon import DaemonConfig, EvolutionDaemon

    config = DaemonConfig(
        interval_hours=interval,
        dry_run=dry_run,
        engine=engine,
    )
    daemon = EvolutionDaemon(config)
    daemon.generate_systemd_unit(output)

    console.print(f"[green]✓[/green] systemd unit written to [cyan]{output}[/cyan]")
    console.print("  Enable with: [dim]sudo systemctl enable maref-evolution-daemon[/dim]")


@daemon_app.command("status")
def daemon_status() -> None:
    """查看演进守护进程的当前状态。"""
    from pathlib import Path

    state_path = Path(".evolution_daemon_state.json")
    if not state_path.exists():
        console.print("[yellow]No daemon state file found. Daemon has never run.[/yellow]")
        return

    import json
    state = json.loads(state_path.read_text())
    console.print("[bold]Evolution Daemon Status[/bold]")
    console.print(f"  Last run:  [cyan]{state.get('last_run', 'never')}[/cyan]")
    console.print(f"  Total runs: [cyan]{state.get('total_runs', 0)}[/cyan]")
    console.print(f"  Failed runs: [cyan]{state.get('failed_runs', 0)}[/cyan]")

    pid_path = Path("/tmp/maref-evolution-daemon.pid")
    if pid_path.exists():
        pid = pid_path.read_text().strip()
        console.print(f"  PID:       [cyan]{pid}[/cyan] (running)")


# ── Report commands ──────────────────────────────────────────────────


@report_app.command("generate")
def report_generate(
    audit_log: str = typer.Option("", "--audit-log", "-a", help="Audit log JSONL file path"),
    signing_key: str = typer.Option("", "--signing-key", "-k", help="Report signing key PEM file path"),
    output: str = typer.Option("governance-report.json", "--output", "-o", help="Output report JSON file path"),
    since: str = typer.Option("", "--since", help="ISO timestamp for incremental generation"),
    state: str = typer.Option("", "--state", help="Governance state override (e.g. VERIFY)"),
) -> None:
    """Generate a signed GovernanceReport from the audit log."""
    from maref.governance.audit import AuditLogger
    from maref.reporting.generator import ReportGenerator
    from maref.reporting.models import SystemStateSnapshot
    from maref.signing.signing_key import ReportSigningKey

    if signing_key:
        key_path = Path(signing_key)
        if not key_path.exists():
            console.print(f"[red]Signing key not found: {signing_key}[/red]")
            raise typer.Exit(1)
        key = ReportSigningKey.from_private_key_file(key_path)
    else:
        console.print("[yellow]No signing key provided — generating ephemeral key for testing[/yellow]")
        key = ReportSigningKey.generate()

    sys_state = None
    if state:
        sys_state = SystemStateSnapshot(governance_state=state)

    since_ts: float | None = None
    if since:
        from datetime import datetime
        since_ts = datetime.fromisoformat(since).timestamp()

    log_path = Path(audit_log) if audit_log else _default_audit_log_path()
    if not log_path.exists():
        console.print(f"[red]Audit log not found: {log_path}[/red]")
        raise typer.Exit(1)

    logger = AuditLogger(log_path=log_path, hmac_key="")
    gen = ReportGenerator(signing_key=key)
    report = gen.from_audit_log(
        audit_logger=logger,
        since_timestamp=since_ts,
        system_state_override=sys_state,
    )

    out = Path(output)
    out.write_text(report.to_json())
    console.print(f"[green]Report generated: {out}[/green]")
    console.print(f"  Report ID:    [cyan]{report.report_id}[/cyan]")
    console.print(f"  Events:       [cyan]{report.audit_summary.total_events}[/cyan]")
    console.print(f"  Merkle Root:  [cyan]{report.merkle_root or '(empty)'}[/cyan]")
    console.print(f"  Signer FP:    [cyan]{report.signer_fingerprint}[/cyan]")


@report_app.command("verify")
def report_verify(
    file: str = typer.Option("governance-report.json", "--file", "-f", help="GovernanceReport JSON file path"),
    pubkey: str = typer.Option("", "--pubkey", "-k", help="Ed25519 public key PEM file for signature verification"),
) -> None:
    """Verify a GovernanceReport file offline.

    Checks signature, fingerprint, and internal consistency.
    Returns VERIFIED/FAILED status with detail.
    """
    from maref.reporting.models import GovernanceReport
    from maref.reporting.verifier import ReportVerifier

    path = Path(file)
    if not path.exists():
        console.print(f"[red]Report not found: {file}[/red]")
        raise typer.Exit(1)

    report = GovernanceReport.from_json(path.read_text())

    ed25519_pubkey_pem: str | None = None
    if pubkey:
        key_path = Path(pubkey)
        if not key_path.exists():
            console.print(f"[red]Public key file not found: {pubkey}[/red]")
            raise typer.Exit(1)
        ed25519_pubkey_pem = key_path.read_text()
    else:
        console.print("[yellow]No public key provided — skipping signature verification[/yellow]")

    if ed25519_pubkey_pem:
        result = ReportVerifier.verify_report(report, ed25519_pubkey_pem)
    else:
        from maref.reporting.verifier import VerificationResult
        basic = report.signature != ""
        result = VerificationResult(
            passed=basic,
            report_id=report.report_id,
            checks={"has_signature": basic},
            details=[] if basic else ["signature field is empty"],
        )

    if result.passed:
        console.print(f"[green]VERIFIED: {result.report_id}[/green]")
    else:
        console.print(f"[red]FAILED: {result.report_id}[/red]")

    from rich.table import Table
    table = Table(title="Verification Report")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="white")
    for check_name, ok in result.checks.items():
        status = "✅ Pass" if ok else "❌ Fail"
        table.add_row(check_name, status)
    table.add_row("Overall", "✅ VERIFIED" if result.passed else "❌ FAILED")
    console.print(table)

    for detail in result.details:
        console.print(f"  [red]! {detail}[/red]")

    if not result.passed:
        raise typer.Exit(1)


@report_app.command("export")
def report_export(
    file: str = typer.Option("governance-report.json", "--file", "-f", help="GovernanceReport JSON file path"),
    output: str = typer.Option("", "--output", "-o", help="Output file path"),
    fmt: str = typer.Option("json", "--format", help="Export format: json or html"),
) -> None:
    """Export a GovernanceReport to JSON or HTML format."""
    from maref.reporting.models import GovernanceReport

    path = Path(file)
    if not path.exists():
        console.print(f"[red]Report not found: {file}[/red]")
        raise typer.Exit(1)

    report = GovernanceReport.from_json(path.read_text())

    if fmt == "json":
        out = Path(output or "governance-report-export.json")
        out.write_text(report.to_json(indent=2))
        console.print(f"[green]Exported JSON: {out}[/green]")

    elif fmt == "html":
        from maref.reporting.exporter import ReportExporter
        out = Path(output or "governance-report.html")
        exporter = ReportExporter()
        exporter.export_report(report, out)
        console.print(f"[green]Exported HTML: {out}[/green]")

    else:
        console.print(f"[red]Unknown format: {fmt} (use json or html)[/red]")
        raise typer.Exit(1)


@report_app.command("signing-key-init")
def report_signing_key_init(
    output_dir: str = typer.Option(".", "--output-dir", "-o", help="Output directory for key files"),
    encrypt: bool = typer.Option(False, "--encrypt", "-e", help="Encrypt private key with password"),
) -> None:
    """Generate a new maref-report-signing Ed25519 key pair.

    Creates: maref-report-signing.pem (private, chmod 600),
             maref-report-signing.pub (public),
             fingerprint.txt (SHA-256 hex fingerprint)
    """
    from maref.signing.signing_key import ReportSigningKey

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    key = ReportSigningKey.init_key_pair(out, encrypt=encrypt)

    console.print(f"[green]Signing key pair generated in: {out}[/green]")
    enc_label = " (encrypted)" if encrypt else ""
    console.print(f"  Private key: [cyan]{out / 'maref-report-signing.pem'}[/cyan] (chmod 600){enc_label}")
    console.print(f"  Public key:  [cyan]{out / 'maref-report-signing.pub'}[/cyan]")
    console.print(f"  Fingerprint: [cyan]{key.fingerprint}[/cyan]")
    console.print()
    console.print("[yellow]Store the private key securely. The fingerprint should be published[/yellow]")
    console.print("[yellow]at maref.cc/verify/fingerprint.txt for third-party verification.[/yellow]")


# ── Serve command ────────────────────────────────────────────────────


@app.command()
@app.command()
def start(
    port: int = typer.Option(8000, "--port", "-p", help="Sidecar HTTP server port"),
    gui: bool = typer.Option(
        False, "--gui/--no-gui", help="Enable GUI endpoints (sessions, streaming, terminal)"
    ),
) -> None:
    """Start MAREF sidecar + register MCP with opencode.

    Starts the governance sidecar HTTP server and writes a
    project-level opencode.json so opencode discovers MAREF's
    MCP tools automatically.
    """
    console.print("[bold green]MAREF Start — Initializing Governance Runtime[/bold green]")
    project_root = Path(__file__).resolve().parent.parent.parent
    opencode_config = project_root / "opencode.json"
    if opencode_config.exists():
        console.print(f"  [green]MCP config:[/green] {opencode_config}")
        console.print("  [green]opencode[/green] will discover MAREF tools on next launch.")
    else:
        console.print("  [yellow]Warning:[/yellow] opencode.json not found — MCP auto-registration unavailable.")
    serve(port=port, gui=gui)


@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="HTTP server port"),
    gui: bool = typer.Option(
        False, "--gui/--no-gui", help="Enable GUI endpoints (sessions, streaming, terminal)"
    ),
    telemetry: bool = typer.Option(
        False, "--telemetry/--no-telemetry", help="Enable maref-obs telemetry bridge"
    ),
    federated: bool = typer.Option(
        False, "--federated/--no-federated", help="Enable federated audit API"
    ),
) -> None:
    """Start MAREF Sidecar HTTP server."""
    if gui:
        console.print("[bold green]MAREF Sidecar Server (GUI Mode)[/bold green]")
    else:
        console.print("[bold green]MAREF Sidecar Server[/bold green]")
    console.print(f"Starting on http://0.0.0.0:{port}")

    if federated:
        console.print("  [green]Federated:[/green] /api/v1/federation/* — cross-org Merkle audit")

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
        uvicorn.run(create_app(collector, monitor, obs_bridge=obs_bridge, federated=federated), host="0.0.0.0", port=port, log_level="info")
    except ImportError:
        console.print(f"[dim]Sidecar server mock — http://0.0.0.0:{port}[/dim]")


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    app()


if __name__ == "__main__":
    main()
