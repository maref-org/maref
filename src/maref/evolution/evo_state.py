from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SNAPSHOT_FILES = {
    "gene_pool": "gene_pool.yaml",
    "ruins_pool": "ruins_pool.yaml",
    "market_logs": "market_logs.yaml",
    "death_records": "death_records.yaml",
    "pheromone_logs": "pheromone_logs.yaml",
    "system_snapshot": "system_snapshot.yaml",
    "metrics_timeseries": "metrics_timeseries.yaml",
}


class EvoStateManager:
    def __init__(self, base_dir: str | Path = "/tmp/maref_evo_orchestrator") -> None:
        self._base_dir = Path(base_dir)

    def start_cycle(self, cycle: int) -> Path:
        snapshot = self._snapshot_dir(cycle)
        snapshot.mkdir(parents=True, exist_ok=True)
        return snapshot

    def write_snapshot(
        self,
        cycle: int,
        gene_pool: list[dict[str, Any]] | None = None,
        ruins_pool: list[dict[str, Any]] | None = None,
        market_logs: list[dict[str, Any]] | None = None,
        death_records: list[dict[str, Any]] | None = None,
        pheromone_logs: list[dict[str, Any]] | None = None,
        system_snapshot: dict[str, Any] | None = None,
        metrics_timeseries: list[dict[str, Any]] | None = None,
    ) -> Path:
        snapshot = self.start_cycle(cycle)
        payload = {
            "gene_pool": gene_pool or [],
            "ruins_pool": ruins_pool or [],
            "market_logs": market_logs or [],
            "death_records": death_records or [],
            "pheromone_logs": pheromone_logs or [],
            "system_snapshot": system_snapshot or {},
            "metrics_timeseries": metrics_timeseries or [],
        }
        for key, file_name in SNAPSHOT_FILES.items():
            self._write_yaml(snapshot / file_name, payload[key])
        return snapshot

    def load_snapshot(self, cycle: int) -> dict[str, Any]:
        snapshot = self._snapshot_dir(cycle)
        loaded: dict[str, Any] = {}
        for key, file_name in SNAPSHOT_FILES.items():
            path = snapshot / file_name
            loaded[key] = self._read_yaml(path) if path.exists() else []
        return loaded

    def _snapshot_dir(self, cycle: int) -> Path:
        return self._base_dir / f"cycle_{cycle}" / "snapshot"

    @staticmethod
    def _write_yaml(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True), encoding="utf-8")

    @staticmethod
    def _read_yaml(path: Path) -> Any:
        return yaml.safe_load(path.read_text(encoding="utf-8"))


__all__ = ["EvoStateManager", "SNAPSHOT_FILES"]
