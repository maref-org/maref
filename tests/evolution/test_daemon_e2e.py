from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from maref.evolution.daemon import DaemonConfig, EvolutionDaemon
from maref.evolution.daily_loop import DailyEvolutionResult


@pytest.mark.slow
def test_daemon_run_once_increments_state(tmp_path: Path) -> None:
    config = DaemonConfig(
        vault_dir=str(tmp_path / ".evolution_vault"),
        state_file=str(tmp_path / "state.json"),
        dry_run=False,
        interval_hours=0.0,
    )
    daemon = EvolutionDaemon(config)

    fake_result = DailyEvolutionResult(
        day="2026-06-28",
        phases=["test"],
        dry_run=False,
        real_writes_enabled=True,
        priority="low",
        stop_reason="test",
    )

    with patch.object(daemon._loop, "run_once", return_value=fake_result):
        asyncio.run(daemon.run_once())

    assert daemon._state.total_runs == 1
    assert daemon._state.failed_runs == 0


@pytest.mark.slow
def test_daemon_run_once_handles_none_result(tmp_path: Path) -> None:
    config = DaemonConfig(
        vault_dir=str(tmp_path / ".evolution_vault"),
        state_file=str(tmp_path / "state.json"),
        dry_run=False,
        interval_hours=0.0,
    )
    daemon = EvolutionDaemon(config)

    with patch.object(daemon._loop, "run_once", return_value=None):
        asyncio.run(daemon.run_once())

    assert daemon._state.total_runs == 1
    assert daemon._state.failed_runs == 1
