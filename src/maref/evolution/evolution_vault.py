from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class EvolutionVault:
    def __init__(self, base_dir: str | Path = ".evolution_vault") -> None:
        self._base_dir = Path(base_dir)

    def start_day(self, day: str) -> Path:
        path = self._day_dir(day)
        path.mkdir(parents=True, exist_ok=True)
        self._ensure_yaml(path / "hypotheses.yaml", [])
        self._ensure_yaml(path / "experiment_results.yaml", [])
        return path

    def write_metrics_snapshot(self, day: str, metrics: dict[str, Any]) -> Path:
        path = self.start_day(day) / "metrics_snapshot.yaml"
        self._write_yaml(path, metrics)
        return path

    def write_hypothesis_record(self, day: str, record: dict[str, Any]) -> Path:
        path = self.start_day(day) / "hypotheses.yaml"
        records = self._read_yaml(path) or []
        records.append(record)
        self._write_yaml(path, records)
        return path

    def write_experiment_result(self, day: str, record: dict[str, Any]) -> Path:
        path = self.start_day(day) / "experiment_results.yaml"
        records = self._read_yaml(path) or []
        records.append(record)
        self._write_yaml(path, records)
        return path

    def write_daily_report(self, day: str, content: str) -> Path:
        path = self.start_day(day) / "daily_report.md"
        path.write_text(content, encoding="utf-8")
        return path

    def write_next_plan(self, day: str, plan: dict[str, Any]) -> Path:
        path = self.start_day(day) / "next_plan.yaml"
        self._write_yaml(path, plan)
        return path

    def load_day(self, day: str) -> dict[str, Any]:
        path = self._day_dir(day)
        return {
            "metrics_snapshot": self._read_optional(path / "metrics_snapshot.yaml", {}),
            "hypotheses": self._read_optional(path / "hypotheses.yaml", []),
            "experiment_results": self._read_optional(path / "experiment_results.yaml", []),
            "daily_report": (path / "daily_report.md").read_text(encoding="utf-8")
            if (path / "daily_report.md").exists()
            else "",
            "next_plan": self._read_optional(path / "next_plan.yaml", {}),
        }

    def _day_dir(self, day: str) -> Path:
        return self._base_dir / day

    @staticmethod
    def _ensure_yaml(path: Path, default: Any) -> None:
        if not path.exists():
            EvolutionVault._write_yaml(path, default)

    @staticmethod
    def _write_yaml(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True), encoding="utf-8")

    @staticmethod
    def _read_yaml(path: Path) -> Any:
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    @staticmethod
    def _read_optional(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        value = EvolutionVault._read_yaml(path)
        return default if value is None else value


__all__ = ["EvolutionVault"]
