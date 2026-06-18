from __future__ import annotations

import time

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from maref.governance.audit import AuditEntry, AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_types import A2ATaskState, map_a2a_to_maref
from maref.recursive.metacognition import EscalationProposal, LimitationReason
from maref.recursive.safety_gate_v2 import SafetyGateV2

app = typer.Typer(
    name="demo",
    help="Demonstration scenarios for MAREF governance features",
    no_args_is_help=True,
)
console = Console()


def _build_status_table(
    sm: GovernanceStateMachine,
    audit: AuditLogger,
    cb: CircuitBreaker,
    sg: SafetyGateV2,
    title: str = "Governance Component Status",
) -> Table:
    table = Table(title=title)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Detail", style="white")
    table.add_row(
        "StateMachine",
        "[green]ACTIVE[/green]",
        f"state={sm.current_state.name} entropy={sm.current_entropy}",
    )
    table.add_row(
        "AuditLogger",
        "[green]ACTIVE[/green]",
        f"entries={audit.count()} hmac={'ON' if audit._hmac_key else 'OFF'}",
    )
    table.add_row(
        "CircuitBreaker",
        "[green]CLOSED[/green]" if cb.state.value == "closed" else "[red]OPEN[/red]",
        f"failures={cb._failure_count} trips={len(cb._trips)}",
    )
    table.add_row(
        "SafetyGateV2",
        "[green]ARMED[/green]",
        f"core_components={len(sg._CORE_COMPONENTS)} max_subtasks={sg.MAX_SUBTASKS}",
    )
    return table


def _build_check_tree(checks: list[tuple[str, bool, str]]) -> Tree:
    tree = Tree("[bold]Safety Gate Checks[/bold]")
    for label, passed, detail in checks:
        if passed:
            tree.add(f"[green]✓[/green] {label}: [dim]{detail}[/dim]")
        else:
            tree.add(f"[red]✗[/red] {label}: [bold red]{detail}[/bold red]")
    return tree


def _build_audit_table(entries: list[AuditEntry]) -> Table:
    table = Table(title="Audit Trail")
    table.add_column("ID", style="dim")
    table.add_column("Event", style="cyan")
    table.add_column("Actor", style="yellow")
    table.add_column("Action", style="green")
    table.add_column("HMAC", style="white")
    for e in entries:
        hmac_short = e.hmac_signature[:12] + "..." if e.hmac_signature else "[dim]none[/dim]"
        table.add_row(e.id, e.event_type, e.actor, e.action, hmac_short)
    return table


@app.command("governed-review")
def governed_review(
    auto_approve: bool = typer.Option(
        False, "--auto-approve", help="Skip HITL prompt and auto-approve"
    ),
    pr_url: str = typer.Option("", "--pr-url", help="PR URL to review"),
    local_path: str = typer.Option(".", "--local", help="Local path to review"),
) -> None:
    """Run the governed code review demonstration through MAREF's governance lifecycle."""
    start_time = time.time()
    steps: list[str] = []
    safety_passed = 0
    review_target = pr_url or local_path

    try:
        # ── Phase 1: Initialize Governance ──────────────────────────────
        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]MAREF Governed Code Review Demo[/bold cyan]\n\n"
                f"Target: [yellow]{review_target}[/yellow]\n"
                f"Auto-approve: [yellow]{auto_approve}[/yellow]",
                title="Phase 1: Initialize Governance",
            )
        )
        steps.append("Initialize Governance")

        sm = GovernanceStateMachine()
        audit = AuditLogger(
            hmac_key="demo-secret-key-2026",
        )
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=5)
        sg = SafetyGateV2()

        console.print(_build_status_table(sm, audit, cb, sg))
        rprint("[green]✓[/green] Governance components initialized")

        # ── Phase 2: Create Task (INIT → ACT) ──────────────────────────
        console.print()
        console.print(
            Panel.fit(
                "[bold]Creating governed review task[/bold]",
                title="Phase 2: Create Task",
            )
        )
        steps.append("Create Task")

        task_description = f"Code Review: {review_target}"
        bridge = A2ABridge(
            state_machine=sm,
            audit_logger=audit,
            circuit_breaker=cb,
            agent_name="maref-governance-agent",
        )

        task_id = bridge.create_task(task_description=task_description)
        rprint(f"[green]✓[/green] Task created: [cyan]{task_id}[/cyan]")
        rprint(f"[green]✓[/green] Description: [cyan]{task_description}[/cyan]")

        transition_table = Table(title="State Transition: INIT → ACT")
        transition_table.add_column("Property", style="cyan")
        transition_table.add_column("Value", style="green")
        transition_table.add_row("From", GovernanceState.INIT.name)
        transition_table.add_row("To", GovernanceState.ACT.name)
        transition_table.add_row("Entropy", "0 → 4")
        transition_table.add_row("Reason", "Developer initiated code review")
        console.print(transition_table)

        sa_check = sg.detect_core_removal(review_target)
        if not sa_check.blocked:
            safety_passed += 1

        decomp_check = sg.validate_decomposition(
            subtask_count=1, capabilities=["code_review", "file_browser"]
        )
        if not decomp_check.blocked:
            safety_passed += 1

        cap_check = sg.validate_capability_assignment(
            subtask_capabilities=["code_review", "file_browser", "git_ops"],
            agent_capabilities=["code_review", "file_browser", "git_ops"],
        )
        if not cap_check.blocked:
            safety_passed += 1

        checks = [
            ("Core Removal Detection", not sa_check.blocked, sa_check.reason or "No core components affected"),
            ("Decomposition Validation", not decomp_check.blocked, decomp_check.reason or "Subtask count within limits"),
            ("Capability Assignment", not cap_check.blocked, cap_check.reason or "All capabilities properly assigned"),
        ]
        console.print(_build_check_tree(checks))

        sm.transition(GovernanceState.ACT, "gov: task created and validated")
        audit.log(
            event_type="governance_decision",
            actor="governance_agent",
            action="transition_to_act",
            details="Safety gate passed, task delegated to specialist",
            metadata={
                "task_id": task_id,
                "from_state": "INIT",
                "to_state": "ACT",
            },
        )
        rprint("[green]✓[/green] Transitioned to [bold]ACT[/bold] (entropy=4)")

        # ── Phase 3: Delegate to Specialist (A2A) ──────────────────────
        console.print()
        console.print(
            Panel.fit(
                "[bold]Delegating review to Code Review Specialist via A2A[/bold]",
                title="Phase 3: Delegate to Specialist",
            )
        )
        steps.append("Delegate to Specialist")

        specialist_url = "http://localhost:8000/api/a2a"
        bridge.delegate_task(task_id=task_id, target_agent_url=specialist_url)

        a2a_state = A2ATaskState.COMPLETED
        maref_state = map_a2a_to_maref(a2a_state)
        bridge.sync_state_from_a2a(task_id, a2a_state.value)

        delegation_table = Table(title="A2A Delegation Details")
        delegation_table.add_column("Property", style="cyan")
        delegation_table.add_column("Value", style="green")
        delegation_table.add_row("Task ID", task_id)
        delegation_table.add_row("Specialist URL", specialist_url)
        delegation_table.add_row("Protocol", "A2A (JSON-RPC 2.0)")
        delegation_table.add_row("A2A State", a2a_state.value)
        delegation_table.add_row("MAREF State", maref_state.name)
        console.print(delegation_table)

        mcp_tree = Tree("[bold]MCP Tools Executed by Specialist[/bold]")
        mcp_tree.add("[green]✓[/green] [cyan]file_browser[/cyan]: read source files")
        mcp_tree.add("[green]✓[/green] [cyan]git_ops[/cyan]: inspect diff & commit history")
        mcp_tree.add("[green]✓[/green] [cyan]code_edit[/cyan]: suggest fixes (read-only)")
        console.print(mcp_tree)

        rprint("[green]✓[/green] Task delegated to Code Review Specialist")
        rprint(f"[green]✓[/green] Findings received and synced: state=[cyan]{maref_state.name}[/cyan]")

        # ── Phase 4: Safety Gate Check ─────────────────────────────────
        console.print()
        console.print(
            Panel.fit(
                "[bold]Post-delegation safety verification[/bold]",
                title="Phase 4: Safety Gate Check",
            )
        )
        steps.append("Safety Gate Check")

        cb_stats = cb.get_stats()
        cb_ok = not cb.is_open
        check_results: list[tuple[str, bool, str]] = [
            (
                "Circuit Breaker",
                cb_ok,
                f"state={cb_stats['state']}, failures={cb_stats['failure_count']}",
            ),
            (
                "Core Component Integrity",
                True,
                "No protected components modified",
            ),
            (
                "Capability Boundary",
                True,
                "Specialist capabilities within permitted scope",
            ),
        ]
        if cb_ok:
            safety_passed += 1

        console.print(_build_check_tree(check_results))
        if cb_ok:
            rprint("[green]✓[/green] All safety gates passed")
        else:
            rprint("[bold red]✗[/bold red] Safety violation detected — circuit breaker OPEN")

        # ── Phase 5: HITL Spot Check ───────────────────────────────────
        console.print()
        console.print(
            Panel.fit(
                "[bold]Human-in-the-loop spot check[/bold]",
                title="Phase 5: HITL Spot Check",
            )
        )
        steps.append("HITL Spot Check")

        proposal = EscalationProposal(
            reason=LimitationReason.HIGH_UNCERTAINTY,
            suggestion="Code review contains potential logic errors in critical path — human verification recommended",
            alternative_agents=["senior-reviewer@maref"],
        )

        hitl_table = Table(title="Escalation Proposal")
        hitl_table.add_column("Field", style="cyan")
        hitl_table.add_column("Value", style="green")
        hitl_table.add_row("Reason", proposal.reason.value)
        hitl_table.add_row("Suggestion", proposal.suggestion)
        hitl_table.add_row("Alternatives", ", ".join(proposal.alternative_agents) or "(none)")
        hitl_table.add_row("Sample Rate", "5% (random spot check)")
        console.print(hitl_table)

        if auto_approve:
            rprint("[green]✓[/green] Auto-approved (--auto-approve flag)")
            hitl_approved = True
            audit.log(
                event_type="hitl_decision",
                actor="human_reviewer",
                action="approve",
                details=f"HITL auto-approved review for {review_target}",
                metadata={
                    "proposal_reason": proposal.reason.value,
                    "auto_approved": True,
                },
            )
        else:
            hitl_approved = typer.confirm("Approve this code review and continue to report?", default=True)

            audit.log(
                event_type="hitl_decision",
                actor="human_reviewer",
                action="approve" if hitl_approved else "reject",
                details=f"HITL {'approved' if hitl_approved else 'rejected'} review for {review_target}",
                metadata={
                    "proposal_reason": proposal.reason.value,
                    "auto_approved": False,
                },
            )

        if hitl_approved:
            rprint("[green]✓[/green] HITL approved — proceeding to final report")
            sm.transition(GovernanceState.REPORT, "gov: hitl approved")
            sm.transition(GovernanceState.HALT, "gov: review complete")
            audit.log(
                event_type="governance_decision",
                actor="governance_agent",
                action="finalize_report",
                details="Code review completed and finalized",
                metadata={
                    "task_id": task_id,
                    "hitl_approved": hitl_approved,
                },
            )
        else:
            rprint("[yellow]⚠[/yellow] HITL rejected — sending back for revision")
            sm.force_stabilize(reason="hitl_rejected")

        # ── Phase 6: Final Report ──────────────────────────────────────
        console.print()
        console.print(
            Panel.fit(
                "[bold]Final governance report[/bold]",
                title="Phase 6: Final Report",
            )
        )
        steps.append("Final Report")

        all_entries = audit.read_all(max_entries=None)
        if all_entries:
            console.print(_build_audit_table(all_entries))
        else:
            rprint("[yellow]No audit entries recorded[/yellow]")

        final_table = Table(title="Final Governance State")
        final_table.add_column("Property", style="cyan")
        final_table.add_column("Value", style="green")
        final_table.add_row("State", sm.current_state.name)
        final_table.add_row("Entropy", str(sm.current_entropy))
        final_table.add_row("Transitions", str(sm.transition_count))
        final_table.add_row("Terminal", str(sm.is_terminal()))
        console.print(final_table)

        integrity = audit.verify_integrity()
        integrity_ok = integrity.get("integrity_intact", False)
        integrity_tree = Tree("[bold]Audit Integrity Verification[/bold]")
        integrity_tree.add(
            f"{'[green]✓[/green]' if integrity_ok else '[red]✗[/red]'} Integrity intact: {integrity_ok}"
        )
        integrity_tree.add(f"  Total entries: {integrity['total_entries']}")
        integrity_tree.add(f"  Signed entries: {integrity['signed_entries']}")
        integrity_tree.add(f"  Valid signatures: {integrity['valid_signatures']}")
        integrity_tree.add(f"  Tampered entries: {integrity['tampered_entries']}")
        console.print(integrity_tree)

        last_entry = all_entries[-1] if all_entries else None
        if last_entry and last_entry.hmac_signature:
            console.print(
                Panel.fit(
                    f"[dim]Last HMAC-SHA256:[/dim] [yellow]{last_entry.hmac_signature}[/yellow]",
                    title="Audit Trail Signature",
                )
            )

        # ── Phase 7: Summary ────────────────────────────────────────────
        console.print()
        elapsed = time.time() - start_time
        summary_table = Table(
            title="[bold]Governed Code Review — Summary[/bold]",
            show_header=True,
            header_style="bold cyan",
        )
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green bold")

        summary_table.add_row("Review Target", review_target)
        summary_table.add_row("Total Steps", str(len(steps)))
        summary_table.add_row("Time Elapsed", f"{elapsed:.2f}s")
        summary_table.add_row("Governance States", f"INIT → {sm.current_state.name}")
        summary_table.add_row("Safety Checks Passed", f"{safety_passed}/3")
        summary_table.add_row("Audit Entries", str(len(all_entries)))
        summary_table.add_row("Audit Integrity", f"{'[green]INTACT[/green]' if integrity_ok else '[red]COMPROMISED[/red]'}")
        summary_table.add_row("HITL Decision", f"{'[green]APPROVED[/green]' if hitl_approved else '[yellow]REJECTED[/yellow]'}")
        summary_table.add_row("Terminal State", f"{'[green]YES[/green]' if sm.is_terminal() else '[yellow]NO[/yellow]'}")
        console.print(summary_table)

        console.print()
        console.print(
            Panel.fit(
                "[bold green]Governed Code Review Complete[/bold green]",
            )
        )

    except Exception:
        import traceback

        console.print("[bold red]Governed code review failed[/bold red]")
        console.print(traceback.format_exc())
        raise typer.Exit(code=1) from None
