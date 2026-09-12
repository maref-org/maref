from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maref.evolution.daily_loop import DailyEvolutionLoop, DailyEvolutionResult

logger = logging.getLogger(__name__)


@dataclass
class DaemonConfig:
    interval_hours: float = 6.0
    max_runs: int = 0
    vault_dir: str | Path = ".evolution_vault"
    state_file: str | Path = ".evolution_daemon_state.json"
    pid_file: str | Path = "/tmp/maref-evolution-daemon.pid"
    dry_run: bool = True
    real_writes: bool = False
    engine: str = "daily"


@dataclass
class DaemonState:
    last_run: str = ""
    total_runs: int = 0
    failed_runs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_run": self.last_run,
            "total_runs": self.total_runs,
            "failed_runs": self.failed_runs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DaemonState:
        return cls(
            last_run=data.get("last_run", ""),
            total_runs=data.get("total_runs", 0),
            failed_runs=data.get("failed_runs", 0),
        )


class EvolutionDaemon:
    def __init__(self, config: DaemonConfig) -> None:
        self._config = config
        self._state = self._load_state()
        self._shutdown = False
        if config.engine == "rel":
            from maref.evolution.rel_adapter import RELAdapter

            self._loop: Any = RELAdapter(dry_run=config.dry_run)
        elif config.engine == "multi":
            from maref.evolution.multi_adapter import MultiAdapter

            self._loop = MultiAdapter(dry_run=config.dry_run)
        elif config.engine == "continuous":
            from maref.evolution.continuous_adapter import ContinuousAdapter

            self._loop = ContinuousAdapter(dry_run=config.dry_run)
        elif config.engine == "saeb":
            from maref.evolution.saeb_adapter import SAEBAdapter

            self._loop = SAEBAdapter(dry_run=config.dry_run)
        elif config.engine == "tla":
            from maref.evolution.tla_adapter import TLAAdapter

            self._loop = TLAAdapter(dry_run=config.dry_run)
        else:
            self._loop = DailyEvolutionLoop(
                vault_dir=config.vault_dir,
                dry_run=config.dry_run,
                real_writes=config.real_writes,
            )

    # ── Core loop ────────────────────────────────────────────────────

    async def run_forever(self) -> None:
        self._setup_signal_handlers()
        self._write_pid_file()
        logger.info(
            "Evolution daemon started (interval=%.1fh, max_runs=%d, pid=%d)",
            self._config.interval_hours,
            self._config.max_runs,
            os.getpid(),
        )

        runs_done = 0
        while not self._shutdown:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Unhandled error in daemon run")

            runs_done += 1
            if self._shutdown:
                break

            if self._config.max_runs > 0 and runs_done >= self._config.max_runs:
                logger.info("Reached max_runs=%d, shutting down", self._config.max_runs)
                break

            interval_seconds = self._config.interval_hours * 3600
            if interval_seconds > 0:
                logger.info("Sleeping for %.1f hours until next run", self._config.interval_hours)
                for _ in range(int(interval_seconds)):
                    if self._shutdown:
                        break
                    await asyncio.sleep(1)

        self._remove_pid_file()
        logger.info("Evolution daemon shut down gracefully")

    async def run_once(self) -> DailyEvolutionResult | None:
        start = time.time()
        logger.info("Daemon run #%d starting", self._state.total_runs + 1)

        try:
            result = self._loop.run_once()
            self._state.total_runs += 1
            if result is None:
                self._state.failed_runs += 1
                logger.warning("Daemon run #%d returned no result", self._state.total_runs)
            else:
                elapsed = time.time() - start
                logger.info(
                    "Daemon run #%d completed in %.1fs (priority=%s)",
                    self._state.total_runs,
                    elapsed,
                    result.priority,
                )
        except Exception:
            self._state.failed_runs += 1
            logger.exception("Daemon run #%d failed", self._state.total_runs + 1)
            result = None

        self._state.last_run = datetime.now(timezone.utc).isoformat()
        self._save_state()
        return result

    # ── State persistence ────────────────────────────────────────────

    def _save_state(self) -> None:
        state_path = Path(str(self._config.state_file))
        try:
            state_path.write_text(json.dumps(self._state.to_dict(), indent=2))
        except OSError:
            logger.exception("Failed to save daemon state to %s", state_path)

    def _load_state(self) -> DaemonState:
        state_path = Path(str(self._config.state_file))
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text())
                return DaemonState.from_dict(data)
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to load daemon state, starting fresh")
        return DaemonState()

    # ── Signal handling ──────────────────────────────────────────────

    def _setup_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self._handle_shutdown)
        except NotImplementedError:
            logger.warning("Signal handlers not supported on this platform")

    def _handle_shutdown(self) -> None:
        logger.info("Shutdown signal received, stopping after current run")
        self._shutdown = True

    # ── PID file management ──────────────────────────────────────────

    def _write_pid_file(self) -> None:
        pid_path = Path(str(self._config.pid_file))
        try:
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            pid_path.write_text(str(os.getpid()))
        except OSError:
            logger.warning("Failed to write PID file %s", pid_path)

    def _remove_pid_file(self) -> None:
        pid_path = Path(str(self._config.pid_file))
        try:
            if pid_path.exists():
                pid_path.unlink()
        except OSError:
            logger.warning("Failed to remove PID file %s", pid_path)

    # ── Service file generation ──────────────────────────────────────

    def generate_launchd_plist(self, output_path: str) -> str:
        executable = sys.executable or "/opt/homebrew/bin/python3"
        pid_path = os.path.abspath(str(self._config.pid_file))
        vault_dir = os.path.abspath(str(self._config.vault_dir))
        state_file = os.path.abspath(str(self._config.state_file))
        user_home = os.path.expanduser("~")

        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.maref.evolution-daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/drive-wait.sh</string>
        <string>{executable}</string>
        <string>-m</string>
        <string>maref.evolution.daemon</string>
        <string>--daemon</string>
        <string>--no-dry-run</string>
        <string>--vault</string>
        <string>{vault_dir}</string>
        <string>--pid-file</string>
        <string>{pid_path}</string>
        <string>--state-file</string>
        <string>{state_file}</string>
        <string>--interval</string>
        <string>{self._config.interval_hours}</string>
        <string>--max-runs</string>
        <string>{self._config.max_runs}</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>{user_home}</string>
    <key>StandardOutPath</key>
    <string>/tmp/maref-evolution-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/maref-evolution-daemon.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{os.environ.get("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin")}</string>
        <key>HOME</key>
        <string>/home/developer</string>
    </dict>
</dict>
</plist>
"""
        if output_path:
            Path(output_path).write_text(plist)
            logger.info("launchd plist written to %s", output_path)
        return plist

    def generate_systemd_unit(self, output_path: str) -> str:
        executable = sys.executable or "/usr/bin/python3"
        script_path = os.path.abspath(sys.argv[0]) if sys.argv else __file__
        pid_path = os.path.abspath(str(self._config.pid_file))
        vault_dir = os.path.abspath(str(self._config.vault_dir))
        state_file = os.path.abspath(str(self._config.state_file))
        unit = f"""[Unit]
Description=MAREF Evolution Daemon
After=network.target

[Service]
Type=simple
ExecStart={executable} {script_path} --daemon \\
    --vault {vault_dir} \\
    --pid-file {pid_path} \\
    --state-file {state_file} \\
    --interval {self._config.interval_hours}
Restart=on-failure
RestartSec=30
PIDFile={pid_path}

[Install]
WantedBy=multi-user.target
"""
        if output_path:
            Path(output_path).write_text(unit)
            logger.info("systemd unit written to %s", output_path)
        return unit


def main() -> None:
    """Entry point: parse args → create daemon → asyncio.run()."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="MAREF evolution daemon — periodic self-evolution loop"
    )
    parser.add_argument("--vault", default=".evolution_vault", help="Evolution vault directory")
    parser.add_argument(
        "--max-runs", type=int, default=0, help="Max evolution cycles (0 = infinite)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True, help="Dry-run mode (default: on)"
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="Enable real file writes (dangerous!)",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        default=False,
        help="Production mode: --no-dry-run + real_writes enabled",
    )
    parser.add_argument(
        "--state-file", default=".evolution_daemon_state.json", help="Daemon state file"
    )
    parser.add_argument(
        "--pid-file",
        default="/tmp/maref-evolution-daemon.pid",
        help="PID file path",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=6.0,
        help="Polling interval in hours",
    )
    parser.add_argument(
        "--engine",
        choices=["daily", "rel", "multi", "continuous", "saeb", "tla"],
        default="daily",
        help="Evolution engine: daily, rel, multi, continuous, saeb, tla",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as a persistent daemon (infinite loop)",
    )
    parser.add_argument(
        "--install-launchd",
        metavar="PATH",
        nargs="?",
        const="/Library/LaunchDaemons/com.maref.evolution-daemon.plist",
        help="Generate and install a macOS launchd plist",
    )
    parser.add_argument(
        "--install-systemd",
        metavar="PATH",
        nargs="?",
        const="/etc/systemd/system/maref-evolution-daemon.service",
        help="Generate and install a Linux systemd unit",
    )

    args = parser.parse_args()

    is_production = args.production
    config = DaemonConfig(
        interval_hours=args.interval,
        max_runs=args.max_runs,
        vault_dir=args.vault,
        state_file=args.state_file,
        pid_file=args.pid_file,
        dry_run=False if is_production else args.dry_run,
        real_writes=is_production,
        engine=args.engine,
    )
    if is_production:
        logger.info("PRODUCTION MODE: dry_run=False, real_writes=True")

    # Service file generation (non-daemon mode, just generate and exit)
    if args.install_launchd:
        daemon = EvolutionDaemon(config)
        daemon.generate_launchd_plist(args.install_launchd)
        logger.info("launchd plist installed at %s", args.install_launchd)
        return

    if args.install_systemd:
        daemon = EvolutionDaemon(config)
        daemon.generate_systemd_unit(args.install_systemd)
        logger.info("systemd unit installed at %s", args.install_systemd)
        return

    # Singleton check: avoid multiple daemon instances
    pid_path = Path(str(config.pid_file))
    if args.daemon and pid_path.exists():
        try:
            existing_pid = int(pid_path.read_text().strip())
            # Check if process is still running
            os.kill(existing_pid, 0)
            logger.error(
                "Daemon already running (PID %d). Remove %s to force start.",
                existing_pid,
                pid_path,
            )
            sys.exit(1)
        except (OSError, ValueError):
            logger.info("Stale PID file %s removed, starting fresh", pid_path)

    if args.daemon:
        daemon = EvolutionDaemon(config)
        asyncio.run(daemon.run_forever())
    else:
        daemon = EvolutionDaemon(config)
        result = daemon._loop.run_once()
        print(result.to_dict() if result else "{}")


if __name__ == "__main__":
    main()
