"""openclaw probe — inventory only until a stable log location is confirmed."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from ..normalize import Event

DEFAULT_HOME = Path(os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")))
_SUFFIXES = {".jsonl", ".json", ".log", ".db", ".sqlite"}


class OpenclawAdapter:
    source = "openclaw"

    def __init__(self, home: Path | str | None = None) -> None:
        self.home = Path(home) if home else DEFAULT_HOME

    def iter_events(self, since: float, limit: int | None = None) -> Iterator[Event]:
        """No stable event stream yet; returns nothing (probe first)."""
        return
        yield  # pragma: no cover

    def probe(self) -> dict[str, object]:
        return probe(self.home)


def probe(home: Path | str | None = None) -> dict[str, object]:
    root = Path(home) if home else DEFAULT_HOME
    files: list[dict[str, object]] = []
    if root.exists():
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _SUFFIXES:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            entry: dict[str, object] = {
                "path": str(path),
                "bytes": size,
                "suffix": path.suffix.lower(),
            }
            if path.suffix.lower() == ".jsonl":
                try:
                    with path.open("r", encoding="utf-8", errors="replace") as handle:
                        entry["lines"] = sum(1 for _ in handle)
                except OSError:
                    entry["lines"] = 0
            files.append(entry)

    agents_dir = root / "agents"
    agency_dir = root / "agency-agents"
    counts = {
        "prompt_agents": len(list(agents_dir.glob("*.prompt.md"))) if agents_dir.exists() else 0,
        "agency_agents": len(list(agency_dir.iterdir())) if agency_dir.exists() else 0,
    }
    return {
        "home": str(root),
        "exists": root.exists(),
        "files": files[:50],
        "file_count": len(files),
        "total_bytes": sum(int(f["bytes"]) for f in files),
        **counts,
    }
