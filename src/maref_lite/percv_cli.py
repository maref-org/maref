"""CLI commands for PERCV integration management.

Usage:
    maref percv research-cycle --topic "..."
    maref percv status
    maref percv sync-cards
    maref percv cost-report
    maref percv ratchet --target TARGET --rounds N --mas-ts
    maref percv cross-analyze --window N
    maref percv meta-diagnose --tag TAG
    maref percv meta-sandbox --diagnosis FILE --rounds N
    maref percv rsi-report --output FILE
    maref percv learn
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from maref.governance.state_machine import GovernanceStateMachine
from maref.integration.percv.cross_dimensional_analyzer import CrossDimensionalAnalyzer
from maref.integration.percv.mas_ts_bridge import MasTSBridge
from maref.integration.percv.meta_ratchet import MetaRatchet
from maref.integration.percv.multi_target_ratchet import (
    ImprovementTarget,
)
from maref.integration.percv.orchestrator import PERCVResearchOrchestrator
from maref.integration.percv.ratchet_bridge import RatchetBridge
from maref.integration.percv.weight_registry import SimpleWeightRegistry
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


# ── RSI Commands ─────────────────────────────────────────────────────


@percv_app.command(name="ratchet")
def ratchet_command(
    target: str = typer.Option("prompts/distill_v1.yaml", "--target", "-t", help="改进目标文件"),
    rounds: int = typer.Option(3, "--rounds", "-n", help="迭代轮数"),
    mas_ts: bool = typer.Option(False, "--mas-ts", help="启用 MAS-TS 验证集成"),
    tag: str = typer.Option("rsi-run", "--tag", help="运行标签"),
) -> None:
    """运行 Ratchet 改进循环。"""
    bridge = RatchetBridge(mas_ts_bridge=MasTSBridge() if mas_ts else None)
    results = bridge.run_improvement_cycle(
        target_file=target,
        budget=rounds,
        use_mas_ts=mas_ts,
    )
    table = Table(title=f"Ratchet Results: {tag}")
    table.add_column("Iter", style="cyan")
    table.add_column("Score", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("MAS-TS", style="green")
    table.add_column("Delta", style="magenta")
    table.add_column("Error", style="red")
    for r in results:
        status_color = "green" if r.status == "keep" else "red"
        table.add_row(
            str(r.iteration),
            f"{r.score:.4f}",
            f"[{status_color}]{r.status}[/]",
            f"{r.mas_ts_score:.1f}" if r.mas_ts_score else "-",
            f"{r.delta:+.4f}" if r.delta else "-",
            r.error or "",
        )
    console.print(table)
    console.print(f"[dim]Best score: {max(r.score for r in results):.4f}[/dim]")

    redline_violations = bridge.check_redlines(target, score=0, mas_ts_score=max(r.mas_ts_score for r in results) if results else 0)
    if redline_violations:
        for v in redline_violations:
            console.print(f"[red]RL: {v}[/red]")


@percv_app.command(name="learn")
def learn_command() -> None:
    """触发学习循环（当前 stub）。"""
    registry = SimpleWeightRegistry()
    console.print(f"[green]Learning weights:[/green] {registry.get_all_weights()}")


@percv_app.command(name="cross-analyze")
def cross_analyze_command(
    window: int = typer.Option(20, "--window", "-w", help="分析窗口大小"),
    results_file: str = typer.Option("", "--results", "-r", help="results.tsv 路径"),
) -> None:
    """运行跨维度交叉影响分析。"""
    history: list[Any] = []
    if results_file:
        p = Path(results_file)
        if p.exists():
            import csv
            with p.open() as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    from maref.integration.percv.multi_target_ratchet import ExperimentResult
                    history.append(ExperimentResult(
                        commit=row.get("commit", ""),
                        metric_value=float(row.get("metric_value", 0)),
                        previous_best=float(row.get("previous_best", 0)),
                        delta=float(row.get("delta", 0)),
                        status=row.get("status", ""),
                        description=row.get("description", ""),
                        memory_mb=float(row.get("memory_mb", 0)),
                        mas_ts_score=float(row.get("mas_ts_score", 0)),
                        mas_ts_level=row.get("mas_ts_level", ""),
                        target_dimension=row.get("target_dimension", ""),
                    ))

    analyzer = CrossDimensionalAnalyzer(history)
    effects = analyzer.detect_cross_effects(window=window)

    if not effects:
        console.print("[yellow]No significant cross-dimensional effects detected.[/yellow]")
        return

    table = Table(title=f"Cross-Dimensional Effects (window={window})")
    table.add_column("Source", style="cyan")
    table.add_column("Target", style="white")
    table.add_column("Effect", style="yellow")
    table.add_column("Confidence", style="green")
    table.add_column("Samples", style="magenta")

    for effect in effects:
        effect_color = "green" if effect.effect_size > 0 else "red"
        table.add_row(
            effect.source_dim,
            effect.target_dim,
            f"[{effect_color}]{effect.effect_size:+.3f}[/]",
            f"{effect.confidence:.2f}",
            str(effect.samples),
        )
    console.print(table)

    pareto = analyzer.recommend_multi_objective({"correctness": 0.7, "testing": 0.6, "code_quality": 0.5, "security": 0.4})
    if pareto:
        console.print("\n[bold]Recommended weight adjustments:[/bold]")
        for dim, weight in pareto.recommended_weights.items():
            current = 0.5
            arrow = "[green]↑[/green]" if weight > current else "[red]↓[/red]"
            console.print(f"  {dim}: {current:.3f} {arrow} {weight:.3f}")


@percv_app.command(name="meta-diagnose")
def meta_diagnose_command(
    tag: str = typer.Option("rsi-run", "--tag", help="运行标签"),
    target: str = typer.Option("prompts/distill_v1.yaml", "--target", "-t", help="改进目标"),
) -> None:
    """诊断 Ratchet 改进停滞。"""
    bridge = RatchetBridge()
    meta = MetaRatchet(ratchet_bridge=bridge)
    imp_target = ImprovementTarget(target)
    diagnosis = meta.diagnose_stagnation(imp_target)

    console.print(Panel(
        f"[bold]Type:[/bold] {diagnosis.diagnosis_type}\n"
        f"[bold]Severity:[/bold] {diagnosis.severity}\n"
        f"[bold]Details:[/bold] {diagnosis.details}\n"
        f"[bold]Suggested:[/bold] {diagnosis.suggested_action}",
        title="Stagnation Diagnosis",
    ))

    with open(".meta_ratchet_diagnosis.json", "w") as f:
        json.dump({
            "type": diagnosis.diagnosis_type,
            "severity": diagnosis.severity,
            "details": diagnosis.details,
            "affected_target": diagnosis.affected_target.value if diagnosis.affected_target else None,
            "suggested_action": diagnosis.suggested_action,
        }, f, indent=2)
    console.print("[dim]Diagnosis saved to .meta_ratchet_diagnosis.json[/dim]")


@percv_app.command(name="meta-sandbox")
def meta_sandbox_command(
    diagnosis: str = typer.Option(".meta_ratchet_diagnosis.json", "--diagnosis", "-d", help="诊断文件路径"),
    rounds: int = typer.Option(10, "--rounds", "-n", help="沙箱测试轮数"),
) -> None:
    """在沙箱中测试 Ratchet 协议变更。"""
    diag_path = Path(diagnosis)
    if not diag_path.exists():
        console.print(f"[red]Diagnosis file not found:[/red] {diag_path}")
        raise typer.Exit(code=1)

    data = json.loads(diag_path.read_text())
    bridge = RatchetBridge()
    meta = MetaRatchet(ratchet_bridge=bridge)

    from maref.integration.percv.meta_ratchet import StagnationDiagnosis
    sd = StagnationDiagnosis(
        diagnosis_type=data.get("type", "saturation"),
        severity=data.get("severity", "low"),
        details=data.get("details", ""),
        affected_target=ImprovementTarget(data["affected_target"]) if data.get("affected_target") else None,
        suggested_action=data.get("suggested_action", ""),
    )

    change = meta.propose_protocol_change(sd)
    if change is None:
        console.print("[yellow]No protocol change proposed (severity too low).[/yellow]")
        return

    console.print(f"[bold]Proposed change:[/bold] {change.config_key} = {change.old_value} → {change.new_value}")
    console.print(f"  Rationale: {change.rationale}")
    console.print(f"  Sandbox rounds: {rounds}")

    if rounds < 10:
        console.print("[red]RL: RSI-RL-002 requires >= 10 sandbox rounds[/red]")
        raise typer.Exit(code=1)

    result = meta.sandbox_test(change, n_rounds=rounds)
    if result.adopted:
        console.print(f"[green]Change adopted! Effect size: {result.improvement:.3f} (Cohen's d)[/green]")
    else:
        console.print(f"[yellow]Change rejected. Effect size: {result.improvement:.3f} (need >0.3)[/yellow]")

    console.print(f"  Old avg: {result.old_avg_score:.4f}")
    console.print(f"  New avg: {result.new_avg_score:.4f}")


@percv_app.command(name="rsi-report")
def rsi_report_command(
    output: str = typer.Option("reports/rsi-report.md", "--output", "-o", help="输出报告路径"),
) -> None:
    """生成 RSI 执行报告。"""
    bridge = RatchetBridge()
    history = bridge.get_history()

    report_lines = [
        "---",
        "title: RSI Daily Report",
        f"date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "---",
        "",
        "## Summary",
        f"- Total iterations: {len(history)}",
        f"- Approved: {sum(1 for r in history if r.approved)}",
        f"- Best score: {max((r.score for r in history), default=0):.4f}",
        "",
        "## Per-Target Results",
    ]

    targets: dict[str, list[Any]] = {}
    for r in history:
        targets.setdefault(r.target, []).append(r)
    for tgt, recs in targets.items():
        scores = [r.score for r in recs if r.approved]
        report_lines.append(f"- **{tgt}**: {len(recs)} runs, best={max(scores):.4f}" if scores else f"- **{tgt}**: {len(recs)} runs, no approvals")

    report_lines.append("")
    report_lines.append("## MAS-TS Scores")
    mas_ts_scores = [r.mas_ts_score for r in history if r.mas_ts_score > 0]
    if mas_ts_scores:
        report_lines.append(f"- Avg: {sum(mas_ts_scores)/len(mas_ts_scores):.1f}")
        report_lines.append(f"- Min: {min(mas_ts_scores):.1f}")
        report_lines.append(f"- Max: {max(mas_ts_scores):.1f}")
    else:
        report_lines.append("- No MAS-TS data")

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report_lines))
    console.print(f"[green]Report saved to:[/green] {out}")


@percv_app.command(name="vault-dashboard")
def vault_dashboard_command(
    vault: str = typer.Option("vault", "--vault", "-v", help="Evolution vault 路径"),
    output: str = typer.Option("", "--output", "-o", help="输出 HTML 路径 (默认 vault/reports/dashboard.html)"),
) -> None:
    """生成 EvolutionVault Chart.js HTML 仪表板。"""
    from maref.vault.evolution_vault import EvolutionVault

    ev = EvolutionVault(vault_path=vault)
    records = ev.load_all()
    if not records:
        console.print("[yellow]Evolution vault is empty — run RSI ratchet first.[/yellow]")
        raise typer.Exit(code=0)

    out_path = Path(output) if output else None
    ev.generate_dashboard_html(output_path=out_path)
    console.print(f"[green]Dashboard generated:[/green] {out_path or ev.reports_dir / 'dashboard.html'}")
    console.print(f"[dim]{len(records)} records, {len(ev.all_targets())} targets[/dim]")


@percv_app.command(name="redlines")
def redlines_command() -> None:
    """显示当前 RSI 宪法红线配置。"""
    from pathlib import Path

    import yaml
    p = Path("configs/rsi_redlines.yaml")
    if not p.exists():
        console.print("[yellow]No rsi_redlines.yaml found.[/yellow]")
        return
    data = yaml.safe_load(p.read_text())
    table = Table(title="RSI Constitutional Redlines")
    table.add_column("Rule ID", style="cyan")
    table.add_column("Severity", style="red")
    table.add_column("Action", style="yellow")
    table.add_column("Description", style="white")
    for rule in data.get("rsi_immutables", []):
        sev_color = "red" if rule.get("severity") == "CRITICAL" else "yellow" if rule.get("severity") == "HIGH" else "white"
        table.add_row(
            rule.get("rule_id", ""),
            f"[{sev_color}]{rule.get('severity', '')}[/]",
            rule.get("auto_action", ""),
            rule.get("description", ""),
        )
    console.print(table)


def main() -> None:
    percv_app()
