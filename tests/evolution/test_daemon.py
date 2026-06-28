from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from maref.evolution.daemon import DaemonConfig, DaemonState, EvolutionDaemon


class TestDaemonState:
    def test_default_state(self) -> None:
        state = DaemonState()
        assert state.last_run == ""
        assert state.total_runs == 0
        assert state.failed_runs == 0

    def test_to_dict_roundtrip(self) -> None:
        original = DaemonState(last_run="2026-01-01T00:00:00", total_runs=5, failed_runs=1)
        data = original.to_dict()
        restored = DaemonState.from_dict(data)
        assert restored.last_run == original.last_run
        assert restored.total_runs == original.total_runs
        assert restored.failed_runs == original.failed_runs

    def test_from_dict_missing_keys(self) -> None:
        state = DaemonState.from_dict({})
        assert state.last_run == ""
        assert state.total_runs == 0
        assert state.failed_runs == 0


class TestDaemonConfig:
    def test_default_values(self) -> None:
        config = DaemonConfig()
        assert config.interval_hours == 6.0
        assert config.dry_run is True
        assert str(config.pid_file) == "/tmp/maref-evolution-daemon.pid"

    def test_custom_values(self) -> None:
        config = DaemonConfig(
            interval_hours=2.0,
            vault_dir="/tmp/vault",
            pid_file="/tmp/test.pid",
            dry_run=False,
        )
        assert config.interval_hours == 2.0
        assert config.dry_run is False

    def test_engine_default_is_daily(self) -> None:
        config = DaemonConfig()
        assert config.engine == "daily"

    def test_engine_rel_creates_rel_adapter(self, tmp_path: Path) -> None:
        config = DaemonConfig(
            state_file=str(tmp_path / "state.json"),
            engine="rel",
        )
        daemon = EvolutionDaemon(config)
        assert "RELAdapter" in type(daemon._loop).__name__

    def test_engine_daily_creates_daily_loop(self, tmp_path: Path) -> None:
        config = DaemonConfig(
            state_file=str(tmp_path / "state.json"),
            engine="daily",
        )
        daemon = EvolutionDaemon(config)
        assert "DailyEvolutionLoop" in type(daemon._loop).__name__


class TestEvolutionDaemon:
    def test_init(self, tmp_path: Path) -> None:
        config = DaemonConfig(state_file=str(tmp_path / "state.json"))
        daemon = EvolutionDaemon(config)
        assert daemon._state.total_runs == 0
        assert daemon._shutdown is False

    def test_init_loads_existing_state(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"last_run": "2026-01-01", "total_runs": 3, "failed_runs": 1}))
        config = DaemonConfig(state_file=str(state_file))
        daemon = EvolutionDaemon(config)
        assert daemon._state.total_runs == 3
        assert daemon._state.failed_runs == 1
        assert daemon._state.last_run == "2026-01-01"

    def test_init_ignores_corrupt_state(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("not-json")
        config = DaemonConfig(state_file=str(state_file))
        daemon = EvolutionDaemon(config)
        assert daemon._state.total_runs == 0

    def test_run_once_success(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        config = DaemonConfig(state_file=str(state_file))
        daemon = EvolutionDaemon(config)

        with patch.object(daemon._loop, "run_once", return_value=MagicMock(priority="low")):
            import asyncio
            asyncio.run(daemon.run_once())

        assert daemon._state.total_runs == 1
        assert daemon._state.failed_runs == 0
        assert state_file.exists()
        loaded = json.loads(state_file.read_text())
        assert loaded["total_runs"] == 1

    def test_run_once_failure(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        config = DaemonConfig(state_file=str(state_file))
        daemon = EvolutionDaemon(config)

        with patch.object(daemon._loop, "run_once", return_value=None):
            import asyncio
            asyncio.run(daemon.run_once())

        assert daemon._state.total_runs == 1
        assert daemon._state.failed_runs == 1

    def test_run_once_exception(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        config = DaemonConfig(state_file=str(state_file))
        daemon = EvolutionDaemon(config)

        with patch.object(daemon._loop, "run_once", side_effect=RuntimeError("boom")):
            import asyncio
            asyncio.run(daemon.run_once())

        assert daemon._state.total_runs == 0
        assert daemon._state.failed_runs == 1

    def test_pid_file_management(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "daemon.pid"
        config = DaemonConfig(pid_file=str(pid_file))
        daemon = EvolutionDaemon(config)

        daemon._write_pid_file()
        assert pid_file.exists()
        assert pid_file.read_text().strip() == str(os.getpid())

        daemon._remove_pid_file()
        assert not pid_file.exists()

    def test_shutdown_sets_flag(self, tmp_path: Path) -> None:
        config = DaemonConfig(state_file=str(tmp_path / "state.json"))
        daemon = EvolutionDaemon(config)
        daemon._handle_shutdown()
        assert daemon._shutdown is True

    def test_run_forever_shutdown_after_one_run(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        pid_file = tmp_path / "daemon.pid"
        config = DaemonConfig(
            state_file=str(state_file),
            pid_file=str(pid_file),
            interval_hours=999.0,
        )
        daemon = EvolutionDaemon(config)

        with (
            patch.object(daemon._loop, "run_once", return_value=MagicMock(priority="low")),
            patch.object(daemon, "_setup_signal_handlers"),
        ):
            # Simulate shutdown after one run
            original_run_once = daemon.run_once

            async def shutdown_after_run() -> None:
                await original_run_once()
                daemon._handle_shutdown()

            daemon.run_once = shutdown_after_run  # type: ignore[method-assign]

            import asyncio
            asyncio.run(daemon.run_forever())

        assert daemon._state.total_runs == 1
        assert not pid_file.exists()

    def test_generate_launchd_plist(self, tmp_path: Path) -> None:
        output = tmp_path / "com.maref.evolution-daemon.plist"
        config = DaemonConfig()
        daemon = EvolutionDaemon(config)

        plist = daemon.generate_launchd_plist(str(output))

        assert output.exists()
        assert "com.maref.evolution-daemon" in plist
        assert "KeepAlive" in plist
        assert "StartInterval" in plist

    def test_generate_systemd_unit(self, tmp_path: Path) -> None:
        output = tmp_path / "maref-evolution-daemon.service"
        config = DaemonConfig()
        daemon = EvolutionDaemon(config)

        unit = daemon.generate_systemd_unit(str(output))

        assert output.exists()
        assert "MAREF Evolution Daemon" in unit
        assert "[Service]" in unit
        assert "Restart=on-failure" in unit


class TestDaemonSignalHandling:
    def test_signal_handlers_not_available(self, tmp_path: Path) -> None:
        config = DaemonConfig(state_file=str(tmp_path / "state.json"))
        daemon = EvolutionDaemon(config)

        with patch("asyncio.get_event_loop", side_effect=NotImplementedError("no signal")):
            daemon._setup_signal_handlers()

