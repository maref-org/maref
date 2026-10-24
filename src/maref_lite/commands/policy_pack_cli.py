from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from maref.governance.policy_pack.builtin import builtin_pack_ids
from maref.governance.policy_pack.loader import (
    PolicyPackLoadError,
    load_policy_pack,
    load_policy_packs,
)

app = typer.Typer(help="Policy pack validation and inspection", no_args_is_help=True)
console = Console()


@app.command("list")
def list_packs() -> None:
    table = Table(title="Built-in policy packs")
    table.add_column("Pack")
    for pack_id in builtin_pack_ids():
        table.add_row(pack_id)
    console.print(table)


@app.command("validate")
def validate(path: Path) -> None:
    try:
        pack = load_policy_pack(path)
    except PolicyPackLoadError as exc:
        console.print(f"[red]ERROR[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[green]OK[/green] {pack.pack_id}@{pack.version} "
        f"jurisdiction={pack.jurisdiction} rules={len(pack.rules)} "
        f"hash={pack.content_hash()[:12]}"
    )


@app.command("validate-dir")
def validate_dir(path: Path) -> None:
    try:
        packs = load_policy_packs(path)
    except PolicyPackLoadError as exc:
        console.print(f"[red]ERROR[/red] {exc}")
        raise typer.Exit(code=1) from exc
    for pack in packs:
        console.print(
            f"[green]OK[/green] {pack.pack_id}@{pack.version} "
            f"jurisdiction={pack.jurisdiction} rules={len(pack.rules)}"
        )
