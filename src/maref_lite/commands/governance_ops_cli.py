"""CLI surface for governance operations (P3 productionization).

Usage:
    maref governance ops content-review --platform xiaohongshu --text "..."
    maref governance ops provenance-register --asset-id a1 --license MIT --content "..."
    maref governance ops evidence-bundle --since-hours 24 --json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from maref.governance.ops_service import get_ops_service

ops_app = typer.Typer(
    name="ops",
    help="Content, provenance, policy, marketplace, evidence, and flywheel operations",
    no_args_is_help=True,
)
console = Console()


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _read_text(text: str, text_file: str) -> str:
    if text_file:
        try:
            return Path(text_file).read_text(encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]Cannot read {text_file}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
    return text


def _fail(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


@ops_app.command("status")
def ops_status(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show configured paths and governance subsystem status."""
    data = get_ops_service().status()
    if json_output:
        typer.echo(_dump(data))
        return
    table = Table(title="Governance Operations")
    table.add_column("Key")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(key, str(value))
    console.print(table)


@ops_app.command("content-review")
def content_review(
    platform: str = typer.Option(..., "--platform", "-p", help="Target platform"),
    text: str = typer.Option("", "--text", "-t", help="Content text"),
    text_file: str = typer.Option("", "--text-file", "-f", help="Read content from file"),
    media_type: list[str] = typer.Option([], "--media-type", "-m", help="Media MIME type"),  # noqa: B008
    ai_generated: bool = typer.Option(False, "--ai-generated", help="Content is AI-generated"),
    disclosure: str = typer.Option("", "--disclosure", help="AI disclosure text"),
    asset_id: str = typer.Option("", "--asset-id", help="Provenance asset id"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Review platform-bound content before publication."""
    payload = {
        "platform": platform,
        "text": _read_text(text, text_file),
        "media_types": media_type,
        "ai_generated": ai_generated,
        "disclosure": disclosure,
        "provenance_asset_id": asset_id,
    }
    data = get_ops_service().review_content(payload)
    if json_output:
        typer.echo(_dump(data))
        return
    color = {"allow": "green", "review": "yellow", "block": "red"}[data["verdict"]]
    console.print(f"[{color}]verdict: {data['verdict']}[/{color}]")
    console.print(f"risk: {data['risk_score']}")
    for reason in data["reasons"]:
        console.print(f"  - {reason}")
    if data["hitl_event_id"]:
        console.print(f"HITL event: {data['hitl_event_id']}")
    if data["evidence_id"]:
        console.print(f"evidence: {data['evidence_id']}")
    if data["redacted_text"] != payload["text"]:
        console.print(f"redacted: {data['redacted_text']}")


@ops_app.command("provenance-register")
def provenance_register(
    asset_id: str = typer.Option(..., "--asset-id", "-a", help="Unique asset id"),
    license_name: str = typer.Option(..., "--license", "-l", help="Asset license"),
    content: str = typer.Option("", "--content", "-c", help="Asset content"),
    content_file: str = typer.Option("", "--content-file", "-f", help="Read content from file"),
    content_hash: str = typer.Option("", "--content-hash", help="Precomputed SHA-256"),
    ai_generated: bool = typer.Option(False, "--ai-generated", help="Asset is AI-generated"),
    model: str = typer.Option("", "--model", help="Generating model"),
    prompt_hash: str = typer.Option("", "--prompt-hash", help="Prompt SHA-256"),
    parent: list[str] = typer.Option([], "--parent", help="Parent asset id"),  # noqa: B008
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Register an asset in the hash-chained provenance ledger."""
    payload = {
        "asset_id": asset_id,
        "content": _read_text(content, content_file) or None,
        "content_hash": content_hash,
        "license": license_name,
        "ai_generated": ai_generated,
        "model": model,
        "prompt_hash": prompt_hash,
        "parent_ids": parent,
    }
    try:
        data = get_ops_service().register_asset(payload)
    except ValueError as exc:
        _fail(str(exc))
        return
    if json_output:
        typer.echo(_dump(data))
        return
    console.print(f"[green]registered {data['asset_id']}[/green]")
    console.print(f"record hash: {data['record_hash']}")


@ops_app.command("provenance-show")
def provenance_show(
    asset_id: str = typer.Argument(..., help="Asset id"),
    lineage: bool = typer.Option(False, "--lineage", help="Show ancestor chain"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show an asset record or its lineage."""
    service = get_ops_service()
    try:
        data = service.lineage(asset_id) if lineage else service.get_asset(asset_id)
    except KeyError:
        data = None
    if data is None:
        _fail(f"asset not found: {asset_id}")
        return
    typer.echo(_dump(data) if json_output else data)


@ops_app.command("provenance-check")
def provenance_check(
    asset_id: str = typer.Argument(..., help="Asset id"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Check license, lineage, and hash-chain publishability."""
    data = get_ops_service().check_publishable(asset_id)
    if json_output:
        typer.echo(_dump(data))
        return
    color = "green" if data["allowed"] else "red"
    console.print(f"[{color}]allowed={data['allowed']}[/{color}] {data['reason']}")


@ops_app.command("provenance-manifest")
def provenance_manifest(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Export the full provenance manifest."""
    typer.echo(_dump(get_ops_service().manifest()))


@ops_app.command("org-check")
def org_check(
    org_id: str = typer.Option(..., "--org", "-o", help="Organization id"),
    role: str = typer.Option(..., "--role", "-r", help="Role id"),
    action: str = typer.Option(..., "--action", "-a", help="Action to evaluate"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Evaluate organization RBAC policy for an action."""
    try:
        data = get_ops_service().org_check(org_id, role, action)
    except ValueError as exc:
        _fail(str(exc))
        return
    if json_output:
        typer.echo(_dump(data))
        return
    console.print(f"decision: {data['decision']} ({data['reason']})")


@ops_app.command("marketplace-check")
def marketplace_check(
    capability: str = typer.Option(..., "--capability", "-c", help="Capability being listed"),
    license_name: str = typer.Option("unknown", "--license", "-l", help="Listing license"),
    publisher_trust: float = typer.Option(0.0, "--trust", "-t", help="Publisher trust 0-1"),
    validation_passed: bool = typer.Option(False, "--validated", help="Validation gates passed"),
    asset_id: str = typer.Option("", "--asset-id", "-a", help="Provenance asset id"),
    signed_card: str = typer.Option("", "--signed-card", help="Signed capability card"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Preflight a marketplace listing against governance gates."""
    data = get_ops_service().marketplace_preflight(
        {
            "capability": capability,
            "license": license_name,
            "publisher_trust": publisher_trust,
            "validation": {"all_passed": validation_passed},
            "asset_id": asset_id,
            "signed_card": signed_card,
        }
    )
    if json_output:
        typer.echo(_dump(data))
        return
    color = "green" if data["allowed"] else "red"
    console.print(f"[{color}]allowed={data['allowed']}[/{color}] risk={data['risk_level']}")
    for reason in data["reasons"]:
        console.print(f"  - {reason}")


@ops_app.command("evidence-bundle")
def evidence_bundle(
    since_hours: float = typer.Option(24.0, "--since-hours", help="Lookback window in hours"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Build an EU AI Act evidence bundle from audit entries."""
    since = time.time() - since_hours * 3600 if since_hours > 0 else None
    data = get_ops_service().evidence_bundle(since=since)
    if json_output:
        typer.echo(_dump(data))
        return
    console.print(f"coverage: {data['coverage']:.2%}")
    console.print(f"evidence: {data['evidence_count']}")
    console.print(f"merkle root: {data['merkle_root']}")
    if data["missing_obligations"]:
        console.print(f"missing: {', '.join(data['missing_obligations'])}")


@ops_app.command("flywheel")
def flywheel(
    since_hours: float = typer.Option(24.0, "--since-hours", help="Lookback window in hours"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Compute governance KPIs and tuning recommendations."""
    since = time.time() - since_hours * 3600 if since_hours > 0 else None
    data = get_ops_service().flywheel_report(since=since)
    if json_output:
        typer.echo(_dump(data))
        return
    kpis = data["kpis"]
    console.print(f"decisions: {kpis['decisions']} deny={kpis['deny']} ask_user={kpis['ask_user']}")
    console.print(f"deny rate: {kpis['deny_rate']:.2%} evidence coverage: {kpis['evidence_coverage']:.2%}")
    for item in data["recommendations"]:
        console.print(f"  - {item.get('action', item)}")


@ops_app.command("feedback")
def feedback(
    evidence_id: str = typer.Option(..., "--evidence-id", "-e", help="Audit evidence id"),
    outcome: str = typer.Option(..., "--outcome", "-o", help="approve/reject/override/false_positive/false_negative"),
    reviewer: str = typer.Option("", "--reviewer", "-r", help="Reviewer id"),
    score: float | None = typer.Option(None, "--score", "-s", help="Optional quality score"),
    notes: str = typer.Option("", "--notes", "-n", help="Reviewer notes"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Record reviewer feedback for the governance flywheel."""
    try:
        data = get_ops_service().record_feedback(
            {
                "evidence_id": evidence_id,
                "outcome": outcome,
                "reviewer": reviewer,
                "score": score,
                "notes": notes,
            }
        )
    except ValueError as exc:
        _fail(str(exc))
        return
    typer.echo(_dump(data) if json_output else data)
