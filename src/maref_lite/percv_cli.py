"""CLI commands for PERCV integration management.

Usage:
    maref percv research-cycle --topic "..."
    maref percv status
    maref percv sync-cards
    maref percv cost-report
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel

from maref.governance.state_machine import GovernanceStateMachine
from maref.integration.percv.orchestrator import PERCVResearchOrchestrator
from maref.integration.test_platform import (
    EvalStatus,
    EvaluationReport,
    EvolutionQualityGate,
    MASEvalObserver,
    TestMode,
)
from maref.integration.test_platform.schema import LayerReport

if TYPE_CHECKING:
    from maref.integration.feature_dev.feature_cycle import CycleSnapshot
    from maref.integration.feature_dev.progress_tracker import ConvergenceReport
    from maref.integration.feature_dev.verification_engine import DeliveryVerdict

percv_app = typer.Typer(
    name="percv",
    help="PERCV integration commands",
    no_args_is_help=True,
)
console = Console()


@percv_app.command()
def research_cycle(
    topic: str = typer.Argument(..., help="Research topic"),
    budget: int = typer.Option(5000, "--budget", "-b", help="Budget in cents"),
) -> None:
    """Run a PERCV research cycle."""
    orch = PERCVResearchOrchestrator()
    result = orch.run_research_cycle(topic=topic)
    console.print(
        Panel(
            str(result.to_dict() if hasattr(result, "to_dict") else result), title="Research Cycle"
        )
    )


@percv_app.command()
def status() -> None:
    """Show PERCV orchestrator status."""
    orch = PERCVResearchOrchestrator()
    console.print_json(
        data={
            "status": orch.status if isinstance(orch.status, str) else orch.status.value,
            "cycle_count": orch.cycle_count,
            "history": orch.get_history(),
        }
    )


@percv_app.command()
def sync_cards() -> None:
    """Sync PERCV cards to knowledge graph."""
    console.print("[yellow]sync-cards not yet implemented[/yellow]")


@percv_app.command(name="cost-report")
def cost_report() -> None:
    """Show LLM cost report."""
    console.print("[yellow]cost-report not yet implemented[/yellow]")


@percv_app.command(name="auto-cycle")
def auto_cycle(
    topic: str = typer.Argument("ecosystem-analysis", help="Research topic"),
    iterations: int = typer.Option(1, "--iterations", "-n", help="Number of cycles"),
) -> None:
    """Run the full closed loop automatically: research → evaluate → evolve → verify."""
    sm = GovernanceStateMachine()
    eval_obs = MASEvalObserver(governance_fsm=sm)
    qg = EvolutionQualityGate()

    report_with_layers = EvaluationReport(
        report_id="auto-cycle",
        agent_id="default-agent",
        test_mode=TestMode.FULL_RUN,
        overall_status=EvalStatus.PASS,
        overall_score=72.0,
        layers=[
            LayerReport(layer_number=1, layer_name="Static Audit", score=90.0),
            LayerReport(layer_number=2, layer_name="Reasoning", score=75.0),
            LayerReport(layer_number=3, layer_name="Action", score=65.0),
            LayerReport(layer_number=4, layer_name="E2E", score=55.0),
            LayerReport(layer_number=5, layer_name="MAS", score=45.0),
        ],
        findings_summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
    )

    orch = PERCVResearchOrchestrator(
        state_machine=sm,
        eval_observer=eval_obs,
        quality_gate=qg,
    )
    orch.initialize()

    for i in range(iterations):
        console.rule(f"[bold]Cycle {i+1}/{iterations}[/bold]")

        r1 = orch.run_research_cycle(topic=f"{topic} (iter {i+1})")
        result_dict = r1.result if r1.result is not None else {}
        console.print(
            f"  [green]research[/green]  → {r1.phase.value}  [{result_dict.get('topic','')}]"
        )

        r2 = orch.run_evaluate_cycle(agent_id="default-agent", report=report_with_layers)
        console.print(
            f"  [blue]evaluate[/blue]   → {r2.phase.value}  [state:{sm.current_state.name}]"
        )

        r3 = orch.run_evolve_cycle(candidate_id="default-agent", score=72.0)
        v = r3.result.get("verdict", "?") if r3.result else "?"
        console.print(f"  [yellow]evolve[/yellow]    → {r3.phase.value}  [verdict:{v}]")

        r4 = orch.run_verify_cycle(agent_id="default-agent")
        console.print(f"  [magenta]verify[/magenta]    → {r4.phase.value}")

        dirs = orch.get_research_directions()
        if dirs:
            for d in dirs[:3]:
                console.print(f"    [dim]feedback [{d['priority']}][/dim] {d['topic']}")

        console.print()

    console.print(
        f"[bold green]Done:[/bold green] {orch.cycle_count} total cycles, {len(orch.get_history())} history entries, sm in {sm.current_state.name}"
    )


@percv_app.command(name="develop-feature")
def develop_feature(
    doc_path: str = typer.Argument(..., help="Path to functional requirements document (Markdown)"),
    feature_name: str = typer.Option(
        "", "--feature-name", "-f", help="Feature name (defaults to doc title)"
    ),
    iterations: int = typer.Option(
        10, "--iterations", "-n", help="Number of recursive evolution cycles (default 10)"
    ),
    output: str = typer.Option("", "--output", "-o", help="Save convergence report to JSON file"),
    verify: bool = typer.Option(
        False, "--verify", "-v", help="Auto-verify against delivery standards after run"
    ),
) -> None:
    """Ingest a requirements doc and run the full development pipeline with recursive feedback.

    Full pipeline per cycle: research \u2192 evaluate \u2192 evolve \u2192 verify \u2192 feedback
    Feedback from low-scoring layers is injected as smart summaries into next cycle's topic.
    After completion, optionally auto-verify against the delivery standards defined in the doc.
    """
    from maref.integration.feature_dev.doc_ingestor import MarkdownDocIngestor
    from maref.integration.feature_dev.feature_cycle import FeatureDevelopmentCycle
    from maref.integration.feature_dev.progress_tracker import ProgressTracker
    from maref.integration.feature_dev.task_generator import TaskGenerator

    doc_path = str(Path(doc_path).expanduser().resolve())
    if not Path(doc_path).exists():
        console.print(f"[red]Document not found:[/red] {doc_path}")
        raise typer.Exit(code=1)

    ingestor = MarkdownDocIngestor()
    doc = ingestor.ingest(doc_path)
    name = feature_name or doc.title

    tg = TaskGenerator(doc)
    tasks = tg.generate()

    console.rule(f"[bold cyan]MAREF Feature Development: {name}[/bold cyan]")
    console.print(f"  [dim]Document:[/dim] {doc_path}")
    console.print(f"  [dim]Iterations:[/dim] {iterations}")
    console.print(
        f"  [dim]Stages detected:[/dim] {', '.join(doc.stages.keys()) if doc.stages else '(none)'}"
    )
    console.print(f"  [dim]Tasks generated:[/dim] {len(tasks)}")
    console.print(f"  [dim]Hypotheses:[/dim] {len(doc.hypotheses)}")
    console.print(f"  [dim]Compliance rules:[/dim] {len(doc.compliance_rules)}")
    console.print(f"  [dim]Cost models:[/dim] {len(doc.cost_models)}")
    console.print()

    cycle_runner = FeatureDevelopmentCycle(doc=doc, tasks=tasks, iterations=iterations)
    tracker = ProgressTracker(feature_name=name)

    for snap in cycle_runner.run():
        tracker.add_snapshot(snap)
        _print_cycle_snapshot(snap, iterations)

    report = tracker.generate_report()
    _print_convergence_report(report)

    import json

    out_path = ""
    if output:
        out_path = output if output.endswith(".json") else f"{output}.json"
    else:
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40]
        out_path = str(reports_dir / f"feature_{safe}.json")

    with open(out_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    console.print(f"[green]Report saved to:[/green] {out_path}")

    if verify:
        console.rule("[bold yellow]Auto-Verification Against Delivery Standards[/bold yellow]")
        from maref.integration.feature_dev.verification_engine import DeliveryVerifier

        verifier = DeliveryVerifier(doc)
        verdict = verifier.verify(report)
        _print_verdict(verdict)
        if output:
            import json

            verdict_path = out_path.replace(".json", "_verdict.json") if output else "verdict.json"
            with open(verdict_path, "w") as f:
                json.dump(verdict.to_dict(), f, indent=2, ensure_ascii=False)
            console.print(f"[green]Verdict saved to:[/green] {verdict_path}")


def _print_cycle_snapshot(snap: CycleSnapshot, total: int) -> None:
    from rich.panel import Panel
    from rich.table import Table

    ARROW = chr(8594)
    c = snap.cycle_number
    status_icon = (
        "[green]PASS[/green]"
        if snap.overall_status.value == "PASS"
        else "[yellow]CONDITIONAL[/yellow]"
        if snap.overall_status.value == "CONDITIONAL"
        else "[red]FAIL[/red]"
    )
    verdict_icon = (
        "[green]approved[/green]"
        if snap.verdict == "approved"
        else "[yellow]conditional[/yellow]"
        if snap.verdict == "conditional"
        else "[red]rejected[/red]"
    )

    panel_lines = [
        "[bold]Cycle {}/{}[/bold]   topic: {}".format(
            c, total, snap.topic[:80] + ("..." if len(snap.topic) > 80 else "")
        ),
    ]

    for h in snap.history_entries:
        step = h.get("step", "?")
        phase = h.get("phase", "?")
        detail = ""
        if step == "research":
            detail = "  topic={}".format(h.get("topic", "")[:60])
        elif step == "evaluate":
            detail = "  score={}".format(h.get("score", "?"))
        elif step == "evolve":
            detail = "  verdict={}".format(h.get("verdict", "?"))
        panel_lines.append(
            f"  [{_step_color(step)}]{step:<10}[/{_step_color(step)}] {ARROW} {phase}{detail}"
        )

    panel_lines.append("")
    panel_lines.append(
        f"  Overall: {snap.overall_score:.1f}/100  {status_icon}  Verdict: {verdict_icon}"
    )
    panel_lines.append(
        f"  Go/No-Go: {snap.go_nogo_decision}  Budget: ${snap.budget_used:.1f}  Duration: {snap.duration_seconds:.1f}s"
    )
    chars = len(snap.artifacts.get("characters", []))
    scripts = len(snap.artifacts.get("scripts", []))
    stages = snap.artifacts.get("stages_covered", set())
    panel_lines.append(f"  Content: {chars} chars, {scripts} scripts, stages={stages}")

    console.print(
        Panel(
            "\n".join(panel_lines),
            title=f"Cycle {c} Pipeline",
            border_style="cyan"
            if snap.overall_score >= 80
            else "yellow"
            if snap.overall_score >= 60
            else "red",
        )
    )

    GAP_ARROW = chr(8594)
    layer_table = Table(title=f"Cycle {c} Layer Scores")
    layer_table.add_column("Layer", style="cyan")
    layer_table.add_column("Score", style="white")
    layer_table.add_column(f"Gap{GAP_ARROW}80", style="yellow")

    for name, score in snap.layer_scores.items():
        gap = max(0.0, 80.0 - score)
        gap_str = f"{gap:.0f}" if gap > 0 else "[green]0[/green]"
        bar = _score_bar(score)
        layer_table.add_row(name, f"{score:.1f}  {bar}", gap_str)
    console.print(layer_table)

    if snap.feedback_injected:
        truncated = snap.feedback_injected[:120] + (
            "..." if len(snap.feedback_injected) > 120 else ""
        )
        console.print(f"  [dim]feedback injected:[/dim] {truncated}")
    console.print()


def _step_color(step: str) -> str:
    return {"research": "green", "evaluate": "blue", "evolve": "yellow", "verify": "magenta"}.get(
        step, "white"
    )


def _score_bar(score: float, width: int = 15) -> str:
    filled = int((score / 100.0) * width)
    empty = width - filled
    color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
    block = chr(9608)
    dot = chr(9617)
    return f"[{color}]{block * filled}[/{color}][dim]{dot * empty}[/dim]"


def _print_convergence_report(report: ConvergenceReport) -> None:
    from rich.table import Table

    ARROW = chr(8594)
    BULLET = chr(8226)

    console.rule("[bold green]Evolution Report[/bold green]")

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value")
    summary.add_row("Total Cycles", str(report.total_cycles))
    summary.add_row("Total Duration", f"{report.total_duration_seconds:.1f}s")
    trend_color = (
        "green"
        if report.overall_trend == "converging"
        else "yellow"
        if report.overall_trend == "fluctuating"
        else "red"
    )
    summary.add_row("Overall Trend", f"[{trend_color}]{report.overall_trend}[/]")
    summary.add_row("Average Score", f"{report.avg_score:.1f}/100")
    deploy_color = "green" if report.deploy_ready else "red"
    deploy_text = "YES" if report.deploy_ready else "NO"
    summary.add_row("Deploy Ready", f"[{deploy_color}]{deploy_text}[/]")
    console.print(summary)

    console.print("\n[bold]Layer Trends:[/bold]")
    trend_table = Table()
    trend_table.add_column("Layer", style="cyan")
    trend_table.add_column("Scores", style="white")
    trend_table.add_column("Direction", style="yellow")
    trend_table.add_column(f"Gap{ARROW}80", style="red")
    trend_table.add_column("Status")

    for t in report.layer_trends:
        scores_str = f" {ARROW} ".join(f"{s:.0f}" for s in t.scores)
        dir_color = (
            "green"
            if t.direction == "converging"
            else "yellow"
            if t.direction == "fluctuating"
            else "red"
        )
        gap_str = f"{t.current_gap:.0f}" if t.current_gap > 0 else "[green]0[/green]"
        status_str = "[green]on track[/green]" if t.is_on_track else "[red]needs attention[/red]"
        trend_table.add_row(
            t.layer_name,
            scores_str,
            f"[{dir_color}]{t.direction}[/]",
            gap_str,
            status_str,
        )
    console.print(trend_table)

    console.print("\n[bold]Deploy Gates:[/bold]")
    gates_table = Table(show_header=False, box=None)
    gates_table.add_column("Gate", style="cyan")
    gates_table.add_column("Result")
    for gate, passed in report.deploy_gates.items():
        icon = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        gates_table.add_row(f"  {gate}", icon)
    console.print(gates_table)

    if report.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for r in report.recommendations[:5]:
            console.print(f"  [dim]{BULLET}[/dim] {r}")
        if len(report.recommendations) > 5:
            console.print(f"  [dim]... and {len(report.recommendations) - 5} more[/dim]")

    console.print()


@percv_app.command(name="feature-status")
def feature_status(
    name: str = typer.Option("", "--name", "-f", help="Feature name filter"),
    latest: int = typer.Option(5, "--latest", "-n", help="Number of recent reports to show"),
) -> None:
    """Show feature development status from latest run reports."""
    import glob
    import json

    reports_dir = Path("reports")
    if not reports_dir.exists():
        console.print("[yellow]No feature development reports found.[/yellow]")
        console.print("[dim]Run [bold]maref percv develop-feature DOC[/bold] first.[/dim]")
        return

    pattern = "feature_*.json"
    if name:
        pattern = f"feature_*{name}*.json"
    matches = sorted(glob.glob(str(reports_dir / pattern)), reverse=True)

    if not matches:
        console.print(f"[yellow]No reports matching '{pattern}' in {reports_dir}.[/yellow]")
        return

    from rich.table import Table

    table = Table(title=f"Feature Development Reports (last {min(len(matches), latest)})")
    table.add_column("Report", style="cyan")
    table.add_column("Cycles", style="white")
    table.add_column("Score", style="yellow")
    table.add_column("Trend", style="green")
    table.add_column("Deploy", style="red")
    table.add_column("Chars", style="white")
    table.add_column("Scripts", style="white")
    table.add_column("Stages", style="blue")

    for fp in matches[:latest]:
        with open(fp) as f:
            data = json.load(f)
        cs = data.get("content_stats", {})
        deploy = "[green]READY[/]" if data.get("deploy_ready") else "[yellow]IN PROGRESS[/]"
        trend_color = "green" if data.get("overall_trend") == "converging" else "yellow"
        table.add_row(
            Path(fp).stem.replace("feature_", "")[:20],
            str(data.get("total_cycles", "?")),
            f"{data.get('avg_score', 0):.1f}",
            f"[{trend_color}]{data.get('overall_trend', '?')}[/]",
            deploy,
            str(cs.get("characters", 0)),
            str(cs.get("scripts", 0)),
            ",".join(cs.get("stages_covered", [])),
        )
    console.print(table)
    console.print(f"\n[dim]Total reports: {len(matches)}[/dim]")


def _print_verdict(verdict: DeliveryVerdict) -> None:
    from rich.table import Table

    BULLET = chr(8226)
    overall_color = "green" if verdict.overall_passed else "red"
    console.print(
        Panel(
            "[{}]{}[/]\nScore: {:.1f}%\n{}".format(
                overall_color,
                "PASSED" if verdict.overall_passed else "FAILED",
                verdict.score,
                verdict.summary,
            ),
            title="Delivery Standards Verification",
            border_style=overall_color,
        )
    )

    vt = Table(title="Per-Check Results")
    vt.add_column("Check", style="cyan")
    vt.add_column("Weight", style="yellow")
    vt.add_column("Result", style="white")
    vt.add_column("Detail", style="dim")

    for item in verdict.items:
        result_icon = "[green]PASS[/green]" if item.passed else "[red]FAIL[/red]"
        vt.add_row(item.check_id, f"{item.weight:.1f}", result_icon, item.detail[:80])
    console.print(vt)

    if not verdict.overall_passed:
        console.print("\n[bold red]Failed checks:[/bold red]")
        for item in verdict.items:
            if not item.passed:
                console.print(f"  {BULLET} [red]{item.check_id}[/red]: {item.detail}")


@percv_app.command(name="develop-verify")
def develop_verify(
    doc_path: str = typer.Argument(..., help="Path to the requirements document"),
    iterations: int = typer.Option(10, "--iterations", "-n", help="Number of evolution cycles"),
    output: str = typer.Option(
        "", "--output", "-o", help="Save full verification report to JSON file"
    ),
) -> None:
    """Run full development pipeline then auto-verify against delivery standards.

    Equivalent to: maref percv develop-feature DOC --iterations N --verify
    """
    from maref.integration.feature_dev.doc_ingestor import MarkdownDocIngestor
    from maref.integration.feature_dev.feature_cycle import FeatureDevelopmentCycle
    from maref.integration.feature_dev.progress_tracker import ProgressTracker
    from maref.integration.feature_dev.task_generator import TaskGenerator
    from maref.integration.feature_dev.verification_engine import DeliveryVerifier

    doc_path_resolved = str(Path(doc_path).expanduser().resolve())
    if not Path(doc_path_resolved).exists():
        console.print(f"[red]Document not found:[/red] {doc_path_resolved}")
        raise typer.Exit(code=1)

    ingestor = MarkdownDocIngestor()
    doc = ingestor.ingest(doc_path_resolved)
    name = doc.title

    tg = TaskGenerator(doc)
    tasks = tg.generate()

    console.rule(f"[bold cyan]MAREF Feature Development + Verify: {name}[/bold cyan]")
    console.print(f"  [dim]Document:[/dim] {doc_path_resolved}")
    console.print(f"  [dim]Iterations:[/dim] {iterations}")
    console.print()

    cycle = FeatureDevelopmentCycle(doc=doc, tasks=tasks, iterations=iterations)
    tracker = ProgressTracker(feature_name=name)

    for snap in cycle.run():
        tracker.add_snapshot(snap)
        _print_cycle_snapshot(snap, iterations)

    report = tracker.generate_report()
    _print_convergence_report(report)

    console.rule("[bold yellow]Auto-Verification Against Delivery Standards[/bold yellow]")
    verifier = DeliveryVerifier(doc)
    verdict = verifier.verify(report)
    _print_verdict(verdict)

    if output:
        import json

        out_path = output if output.endswith(".json") else f"{output}.json"
        with open(out_path, "w") as f:
            json.dump(
                {"verdict": verdict.to_dict(), "report": report.to_dict()},
                f,
                indent=2,
                ensure_ascii=False,
            )
        console.print(f"[green]Full report saved to:[/green] {out_path}")


def main() -> None:
    percv_app()
