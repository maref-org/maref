import json
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from maref.integration.percv.cross_dimensional_analyzer import CrossDimensionalAnalyzer
from maref.integration.percv.meta_ratchet import MetaRatchet, ProtocolChange
from maref.integration.percv.multi_target_ratchet import ImprovementTarget, MultiTargetRatchet
from maref.integration.percv.orchestrator import OrchestratorCycleResult, PERCVResearchOrchestrator
from maref.vault.evolution_vault import EvolutionVault

app = typer.Typer(no_args_is_help=True)
percv_app = app
console = Console()


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


# ── research-cycle command ──────────────────────────────────────────────


@app.command()
def research_cycle(
    topic: str = typer.Argument(..., help="Research topic"),
    budget: int = typer.Option(5000, "--budget", "-b", help="Research budget in tokens"),
) -> None:
    orch = PERCVResearchOrchestrator()
    result = orch.run_research_cycle(topic=topic)

    console.print(
        Panel(
            f"[bold cyan]Research Cycle Complete[/bold cyan]\nTopic: {topic}\nBudget: {budget} tokens"
        )
    )
    console.print(f"Cycle: {result.cycle_id} | Phase: {result.phase.value}")


# ── status command ──────────────────────────────────────────────────────


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    orch = PERCVResearchOrchestrator()
    status_val = getattr(orch, "status", "unknown")
    cycle_count = getattr(orch, "cycle_count", 0)
    history = getattr(orch, "get_history", lambda: [])()

    if json_output:
        console.print_json(
            json.dumps(
                {
                    "status": str(status_val),
                    "cycle_count": cycle_count,
                    "history": history,
                },
                indent=2,
                default=str,
            )
        )
        return

    table = Table(title="PERCV Orchestrator Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Status", str(status_val))
    table.add_row("Cycle Count", str(cycle_count))
    table.add_row("History Entries", str(len(history)))
    console.print(table)


# ── sync-cards command ─────────────────────────────────────────────────


@app.command(name="sync-cards")
def sync_cards() -> None:
    console.print("[yellow]sync-cards: not yet implemented[/yellow]")


# ── cost-report command ────────────────────────────────────────────────


@app.command(name="cost-report")
def cost_report() -> None:
    console.print("[yellow]cost-report: not yet implemented[/yellow]")


# ── auto-cycle command ─────────────────────────────────────────────────


@app.command(name="auto-cycle")
def auto_cycle(
    topic: str = typer.Argument("", help="Research topic"),
    iterations: int = typer.Option(1, "--iterations", "-n", help="Number of cycles"),
    agent_id: str = typer.Option("cli-agent", "--agent-id", "-a", help="Agent ID"),
    candidate_id: str = typer.Option("cli-candidate", "--candidate-id", "-c", help="Candidate ID"),
) -> None:
    orch = PERCVResearchOrchestrator()
    orch.initialize()

    for i in range(iterations):
        iter_topic = topic or f"ecosystem-analysis (iter {i + 1})"
        console.print(f"[bold]Cycle {i + 1}/{iterations}[/bold] — {iter_topic}")

        orch.run_research_cycle(topic=iter_topic)
        orch.run_evaluate_cycle(agent_id=agent_id)
        orch.run_evolve_cycle(candidate_id=candidate_id)
        orch.run_verify_cycle(agent_id=agent_id)

        console.print(
            f"  [green]✓[/green] Cycle {i + 1} complete — total cycles: {orch.cycle_count}"
        )

    directions = orch.get_research_directions()
    if directions:
        console.print("\n[bold]Research Directions (from feedback):[/bold]")
        for d in directions:
            console.print(f"  [{d['priority']}] {d['topic']}")


# ── develop-feature command ─────────────────────────────────────────────


@app.command(name="develop-feature")
def develop_feature(
    feature_doc: str = typer.Argument(..., help="Path to feature document"),
    iterations: int = typer.Option(3, "--iterations", "-i", help="Max iteration rounds"),
    output_dir: str = typer.Option("", "--output", "-o", help="Output directory"),
    verify: bool = typer.Option(
        True, "--verify/--no-verify", help="Run verification after development"
    ),
) -> None:
    doc_path = Path(feature_doc)
    if not doc_path.exists():
        console.print(f"[red]Feature document not found: {feature_doc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Developing feature:[/bold] {doc_path.name}")
    console.print(f"Iterations: {iterations} | Verify: {verify}")


# ── feature-status command ──────────────────────────────────────────────


@app.command(name="feature-status")
def feature_status(
    name: str = typer.Option("", "--name", "-n", help="Feature name filter"),
    latest: int = typer.Option(5, "--latest", "-l", help="Number of latest reports"),
) -> None:
    reports_dir = Path(".missions") / "reports"
    if not reports_dir.exists():
        console.print("[yellow]No feature development reports found.[/yellow]")
        return

    reports = sorted(reports_dir.glob("*.json"), reverse=True)[:latest]
    if name:
        reports = [r for r in reports if name.lower() in r.stem.lower()]

    if not reports:
        console.print(f"[yellow]No matching reports for '{name}'.[/yellow]")
        return

    table = Table(title=f"Feature Reports (latest {len(reports)})")
    table.add_column("Report", style="cyan")
    table.add_column("Date", style="green")
    for r in reports:
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(r.stat().st_mtime))
        table.add_row(r.name, mtime)
    console.print(table)


# ── develop-verify command ──────────────────────────────────────────────


@app.command(name="develop-verify")
def develop_verify(
    feature_doc: str = typer.Argument(..., help="Path to feature document"),
    iterations: int = typer.Option(3, "--iterations", "-i", help="Max iteration rounds"),
    output_dir: str = typer.Option("", "--output", "-o", help="Output directory"),
) -> None:
    doc_path = Path(feature_doc)
    if not doc_path.exists():
        console.print(f"[red]Feature document not found: {feature_doc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Verifying feature:[/bold] {doc_path.name}")
    console.print(f"Iterations: {iterations}")


# ── ratchet command ─────────────────────────────────────────────────────


@app.command()
def ratchet(
    target: str = typer.Option("all", "--target", "-t", help="Improvement target"),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Number of ratchet rounds"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without applying"),
) -> None:
    ratchet_instance = MultiTargetRatchet()
    targets = list(ImprovementTarget) if target == "all" else [ImprovementTarget(target)]

    console.print(f"[bold]Multi-Target Ratchet[/bold] ({len(targets)} targets × {rounds} rounds)")
    if dry_run:
        console.print("[yellow]Dry-run mode — no changes applied[/yellow]")

    for t in targets:
        if dry_run:
            console.print(f"  [dim]Would ratchet: {t.value}[/dim]")
        else:
            next_target = ratchet_instance.next_target()
            console.print(f"  Next target: {next_target.value}")
            for _ in range(rounds):
                if ratchet_instance.should_escalate(t):
                    console.print(f"  [yellow]Escalation needed for {t.value}[/yellow]")
                summary = ratchet_instance.get_target_summary()
                console.print(f"  Target summary: {summary.get(t.value, {})}")


# ── learn command ───────────────────────────────────────────────────────


@app.command()
def learn(
    rounds: int = typer.Option(1, "--rounds", "-r", help="Learning rounds"),
) -> None:
    console.print(f"[yellow]learn: stub — {rounds} rounds not yet implemented[/yellow]")


# ── cross-analyze command (实装) ─────────────────────────────────────────


@app.command(name="cross-analyze")
def cross_analyze_command(
    window: int = typer.Option(20, "--window", "-w", help="Analysis window size"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    analyzer = CrossDimensionalAnalyzer()
    effects = analyzer.detect_cross_effects(window=window)

    if json_output:
        console.print_json(
            json.dumps(
                [
                    {
                        "source": e.source_dim,
                        "target": e.target_dim,
                        "effect_size": round(e.effect_size, 4),
                        "confidence": round(e.confidence, 4),
                    }
                    for e in effects
                ],
                indent=2,
            )
        )
        return

    if not effects:
        console.print(
            "[yellow]No significant cross-dimensional effects detected (window too small or no history).[/yellow]"
        )
        return

    table = Table(title=f"Cross-Dimensional Effects (window={window})")
    table.add_column("Source", style="cyan")
    table.add_column("Target", style="magenta")
    table.add_column("Effect Size", style="yellow")
    table.add_column("Confidence", style="green")
    table.add_column("Samples", style="white")

    for e in effects:
        color = "red" if e.effect_size < 0 else "green"
        table.add_row(
            e.source_dim,
            e.target_dim,
            f"[{color}]{e.effect_size:.4f}[/{color}]",
            f"{e.confidence:.2f}",
            str(e.samples),
        )
    console.print(table)

    pareto = analyzer.recommend_multi_objective(
        current_weights={
            "correctness": 0.3,
            "testing": 0.3,
            "performance": 0.2,
            "code_quality": 0.1,
            "security": 0.1,
        }
    )
    if pareto:
        console.print("\n[bold]Pareto Front Recommendation:[/bold]")
        wt = Table()
        wt.add_column("Dimension", style="cyan")
        wt.add_column("Current", style="yellow")
        wt.add_column("Recommended", style="green")
        for dim in pareto.dimensions:
            cur = pareto.current_scores.get(dim, 0)
            rec = pareto.recommended_weights.get(dim, 0)
            wt.add_row(dim, f"{cur:.3f}", f"{rec:.3f}")
        console.print(wt)


# ── meta-diagnose command (实装) ────────────────────────────────────────


@app.command(name="meta-diagnose")
def meta_diagnose_command(
    target: str = typer.Option("prompts", "--target", "-t", help="Improvement target"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    meta = MetaRatchet()
    t = (
        ImprovementTarget(target)
        if target in {e.value for e in ImprovementTarget}
        else ImprovementTarget.PROMPT_DISTILL
    )

    diag = meta.diagnose_stagnation(t)

    if json_output:
        console.print_json(
            json.dumps(
                {
                    "target": target,
                    "diagnosis_type": diag.diagnosis_type,
                    "severity": diag.severity,
                    "details": diag.details,
                    "suggested_action": diag.suggested_action,
                },
                indent=2,
            )
        )
        return

    console.print(Panel(f"[bold]MetaRatchet Diagnosis[/bold]\nTarget: {target}", expand=False))
    table = Table()
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Diagnosis Type", diag.diagnosis_type)
    severity_color = (
        "red" if diag.severity == "high" else "yellow" if diag.severity == "medium" else "green"
    )
    table.add_row("Severity", f"[{severity_color}]{diag.severity}[/{severity_color}]")
    table.add_row("Details", diag.details)
    table.add_row("Suggested Action", diag.suggested_action)
    console.print(table)

    change = meta.propose_protocol_change(diag)
    if change:
        console.print("\n[bold]Protocol Change Proposal:[/bold]")
        ct = Table()
        ct.add_column("Key", style="cyan")
        ct.add_column("Old", style="yellow")
        ct.add_column("New", style="green")
        ct.add_column("Rationale", style="white")
        ct.add_row(
            change.config_key, str(change.old_value), str(change.new_value), change.rationale
        )
        console.print(ct)
    else:
        console.print("[dim]No protocol change proposed.[/dim]")

    triggers = meta.check_triggers(t)
    if triggers:
        console.print(f"\n[yellow]Active Triggers: {', '.join(triggers)}[/yellow]")


# ── meta-sandbox command (实装) ─────────────────────────────────────────


@app.command(name="meta-sandbox")
def meta_sandbox_command(
    config_key: str = typer.Option(
        "max_consecutive_discards", "--config-key", "-k", help="Config key to test"
    ),
    old_value: str = typer.Option("5", "--old", "-o", help="Old value"),
    new_value: str = typer.Option("4", "--new", "-n", help="New value"),
    rounds: int = typer.Option(10, "--rounds", "-r", help="Number of sandbox rounds"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    meta = MetaRatchet()

    change = ProtocolChange(
        config_key=config_key,
        old_value=old_value,
        new_value=new_value,
        rationale=f"CLI sandbox test: {config_key} {old_value} → {new_value}",
        sandbox_rounds=rounds,
    )

    result = meta.sandbox_test(change, n_rounds=rounds)

    if json_output:
        console.print_json(
            json.dumps(
                {
                    "config_key": config_key,
                    "old_avg_score": round(result.old_avg_score, 4),
                    "new_avg_score": round(result.new_avg_score, 4),
                    "improvement": round(result.improvement, 4),
                    "adopted": result.adopted,
                    "production_safe": result.is_production_safe,
                },
                indent=2,
            )
        )
        return

    improvement_pct = result.improvement * 100
    color = "green" if result.adopted else "red"
    console.print(
        Panel(
            f"[bold]Sandbox Test Results[/bold]\n{config_key}: {old_value} → {new_value} ({rounds} rounds)"
        )
    )
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Before", style="yellow")
    table.add_column("After", style="green")
    table.add_column("Delta", style="white")
    table.add_row(
        "Score",
        f"{result.old_avg_score:.4f}",
        f"{result.new_avg_score:.4f}",
        f"[{color}]{improvement_pct:+.2f}%[/{color}]",
    )
    console.print(table)
    console.print(
        f"Adopted: [{'green' if result.adopted else 'red'}]{result.adopted}[/{'green' if result.adopted else 'red'}]"
    )
    console.print(
        f"Production Safe: [{'green' if result.is_production_safe else 'red'}]{result.is_production_safe}[/]"
    )


# ── rsi-report command (实装) ───────────────────────────────────────────


@app.command(name="rsi-report")
def rsi_report_command(
    vault_path: str = typer.Option("vault", "--vault", "-v", help="EvolutionVault path"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    vault = EvolutionVault(vault_path=vault_path)
    summary = vault.summary_report()
    targets = vault.all_targets()

    if json_output:
        console.print_json(json.dumps(summary, indent=2, default=str))
        return

    console.print(
        Panel(
            f"[bold cyan]RSI EvolutionVault Report[/bold cyan]\nVault: {vault_path}", expand=False
        )
    )
    console.print(
        f"Total Records: {summary['total_records']} | Targets: {summary['total_targets']}"
    )
    console.print(
        f"Keep Rate: {summary['keep_rate']:.1%} ({summary['keeps']} keeps / {summary['discards']} discards)"
    )

    if not targets:
        console.print("[yellow]No targets found in vault — run RSI cycles first.[/yellow]")
        return

    table = Table(title="Target Trends")
    table.add_column("Target", style="cyan")
    table.add_column("Runs", style="white")
    table.add_column("Avg Score", style="yellow")
    table.add_column("Best", style="green")
    table.add_column("Latest", style="blue")
    table.add_column("Trend", style="magenta")
    table.add_column("Keep Rate", style="white")

    for t in targets:
        trend = vault.get_trend(t)
        trend_icon = (
            "↑"
            if trend.score_trend == "improving"
            else "↓"
            if trend.score_trend == "declining"
            else "→"
        )
        table.add_row(
            t,
            str(trend.total_runs),
            f"{trend.avg_score:.4f}",
            f"{trend.best_score:.4f}",
            f"{trend.latest_score:.4f}",
            f"{trend_icon} {trend.score_trend}",
            f"{trend.keep_rate:.0%}",
        )
    console.print(table)


# ── vault-dashboard command (实装) ──────────────────────────────────────


@app.command(name="vault-dashboard")
def vault_dashboard_command(
    vault_path: str = typer.Option("vault", "--vault", "-v", help="EvolutionVault path"),
    open_browser: bool = typer.Option(False, "--open", "-o", help="Open dashboard in browser"),
    output: str = typer.Option("", "--output", "-f", help="Output HTML path"),
) -> None:
    vault = EvolutionVault(vault_path=vault_path)
    records = vault.load_all()

    if not records:
        console.print("[yellow]Vault is empty — no RSI experiment records found.[/yellow]")
        console.print("Run RSI cycles first: [dim]maref percv ratchet[/dim]")
        return

    out_path = output or str(vault.reports_dir / "dashboard.html")
    vault.generate_dashboard_html(output_path=out_path)

    console.print(f"[green]Dashboard written to:[/green] {out_path}")
    console.print(f"Records: {len(records)} | Targets: {len(vault.all_targets())}")

    if open_browser:
        import webbrowser

        webbrowser.open(f"file://{Path(out_path).resolve()}")
        console.print("[green]Dashboard opened in browser.[/green]")


# ── redlines command (实装) ─────────────────────────────────────────────


@app.command()
def redlines(
    config_path: str = typer.Option(
        "configs/rsi_redlines.yaml", "--config", "-c", help="Redlines YAML path"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    import yaml

    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Redlines config not found: {config_path}[/red]")
        raise typer.Exit(code=1)

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    rules = data.get("rsi_immutables", [])
    version = data.get("version", "unknown")

    if json_output:
        console.print_json(json.dumps(data, indent=2, default=str))
        return

    console.print(Panel(f"[bold red]RSI Constitutional Redlines[/bold red] v{version}"))
    table = Table()
    table.add_column("Rule ID", style="red")
    table.add_column("Severity", style="yellow")
    table.add_column("Action", style="magenta")
    table.add_column("Description", style="white")
    table.add_column("Applies To", style="cyan")

    severity_colors = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "blue"}
    for rule in rules:
        sev = rule.get("severity", "")
        sev_colored = (
            f"[{severity_colors.get(sev, 'white')}]{sev}[/{severity_colors.get(sev, 'white')}]"
        )
        table.add_row(
            rule.get("rule_id", ""),
            sev_colored,
            rule.get("auto_action", ""),
            rule.get("description", ""),
            ", ".join(rule.get("applies_to", [])),
        )
    console.print(table)
    console.print(f"\n[dim]Total rules: {len(rules)}[/dim]")


# ── Internal helpers (内部使用) ─────────────────────────────────────────


def _print_cycle_snapshot(result: object) -> None:
    if isinstance(result, OrchestratorCycleResult):
        duration = getattr(result, "completed_at", 0) - getattr(result, "started_at", 0)
        console.print(f"  Phase: {result.phase.value} | Duration: {_fmt_duration(duration)}")


def _step_color(step_index: int, total_steps: int) -> str:
    ratios = [(i + 1) / total_steps for i in range(total_steps)]
    r = ratios[step_index] if step_index < len(ratios) else 1.0
    if r < 0.33:
        return "yellow"
    if r < 0.66:
        return "blue"
    return "green"


def _score_bar(score: float, width: int = 20) -> str:
    filled = int(score * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "green" if score >= 0.7 else "yellow" if score >= 0.4 else "red"
    return f"[{color}]{bar}[/{color}]"


def _print_convergence_report(result: object) -> None:
    if isinstance(result, OrchestratorCycleResult):
        phase = getattr(result, "phase", "unknown")
        console.print(f"Convergence: {phase.value if hasattr(phase, 'value') else phase}")


def _print_verdict(result: object) -> None:
    if isinstance(result, OrchestratorCycleResult):
        console.print(f"Verdict: {getattr(result, 'result', {})}")


# ── Direct entry point ──────────────────────────────────────────────────


def main() -> None:
    app()
