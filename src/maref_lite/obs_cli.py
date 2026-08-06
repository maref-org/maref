"""``maref obs`` — inspect the local observation buffer."""

from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.table import Table

from maref.obs import MarefObsClient, TelemetryLevel

obs_app = typer.Typer(help="Local observation buffer commands", no_args_is_help=True)
console = Console()


@obs_app.command("status")
def obs_status() -> None:
    """Show MarefObs client status and event counts."""
    client = MarefObsClient.get_default()
    path = client.get_buffer_path()

    console.print("[bold]MAREF Obs (maref-obs)[/bold]")
    console.print(f"  Level:       [cyan]{client.level.value}[/cyan]")
    console.print(f"  Session ID:  [dim]{client.session_id}[/dim]")
    console.print(f"  Buffer:      {path or '[red]disabled[/red]'}")

    if client.level == TelemetryLevel.OFF:
        console.print("\n[yellow]Telemetry is OFF. Set MAREF_TELEMETRY_LEVEL to enable.[/yellow]")
        return

    if path and path.exists():
        size = path.stat().st_size
        console.print(f"  Size:        {_fmt_size(size)}")
        counts = client.count_events()
        if counts:
            table = Table(title="Event Counts (today)")
            table.add_column("Event Type", style="cyan")
            table.add_column("Count", style="green")
            for et, cnt in sorted(counts.items()):
                table.add_row(et, str(cnt))
            console.print(table)
        else:
            console.print("  [dim]No events recorded today.[/dim]")
    else:
        console.print("  [dim]Buffer file not yet created.[/dim]")


@obs_app.command("show")
def obs_show(
    last: int = typer.Option(20, "--last", "-n", help="Number of recent events"),
    event_type: str = typer.Option("", "--type", "-t", help="Filter by event type"),
) -> None:
    """Show recent events from the local observation buffer."""
    client = MarefObsClient.get_default()
    events = client.get_all_events()

    if event_type:
        events = [e for e in events if e.get("event_type") == event_type]
    events = events[-last:]

    if not events:
        console.print("[yellow]No matching events found.[/yellow]")
        return

    table = Table(title=f"MarefObs Events (last {len(events)})")
    table.add_column("Seq", style="dim")
    table.add_column("Time", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Metadata", style="white")
    table.add_column("Level", style="yellow")

    for event in events:
        ts = event.get("timestamp", 0)
        time_str = time.strftime("%H:%M:%S", time.localtime(ts))
        meta = event.get("metadata", {})
        meta_str = _fmt_meta(meta)
        table.add_row(
            str(event.get("event_sequence", "")),
            time_str,
            event.get("event_type", "")[:24],
            meta_str[:60],
            client.level.value,
        )
    console.print(table)


@obs_app.command("level")
def obs_level(
    level: str = typer.Argument(
        "status",
        help="Telemetry level: off / basic / standard / detailed, or 'status' to show current",
    ),
) -> None:
    """Get or set the telemetry level for the current session."""
    if level == "status":
        client = MarefObsClient.get_default()
        console.print(f"Current level: [cyan]{client.level.value}[/cyan]")
        return

    normalized = level.strip().lower()
    valid = {lv.value for lv in TelemetryLevel}
    if normalized not in valid:
        console.print(f"[red]Invalid level '{level}'.[/red] Valid: {', '.join(sorted(valid))}")
        raise typer.Exit(code=1)

    client = MarefObsClient.get_default()
    TelemetryLevel.from_env(normalized)
    console.print(f"Level set to [cyan]{normalized}[/cyan] (for this session only)")


def _fmt_size(bytes_count: int) -> str:
    if bytes_count < 1024:
        return f"{bytes_count} B"
    kib = bytes_count / 1024
    if kib < 1024:
        return f"{kib:.1f} KiB"
    mib = kib / 1024
    return f"{mib:.1f} MiB"


def _fmt_meta(meta: dict) -> str:
    items = []
    for k, v in meta.items():
        if isinstance(v, float):
            items.append(f"{k}={v:.2f}")
        else:
            items.append(f"{k}={v}")
    return ", ".join(items)
