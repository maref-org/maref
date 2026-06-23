"""PyInstaller boot entry point for MAREF Sidecar binary.

This script is the entry point for the packaged PyInstaller binary.
It mirrors the logic in maref_lite/cli.py:serve() but as a standalone
script so PyInstaller can trace all imports.
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF Sidecar")
    parser.add_argument("--port", type=int, default=8000, help="HTTP server port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind address")
    parser.add_argument("--gui", action="store_true", help="Enable GUI endpoints")
    parser.add_argument("--telemetry", action="store_true", help="Enable telemetry bridge")
    args = parser.parse_args()

    import uvicorn

    from maref.obs import MarefObsClient
    from sidecar.collector import MockAgentAdapter, ObservationCollector
    from sidecar.monitor import CompositeMonitor
    from sidecar.obs_bridge import ObsBridge
    from sidecar.server import create_app

    collector = ObservationCollector(adapter=MockAgentAdapter())
    monitor = CompositeMonitor()
    obs_bridge = ObsBridge(client=MarefObsClient.get_default()) if args.telemetry else None
    app = create_app(collector, monitor, obs_bridge=obs_bridge)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
