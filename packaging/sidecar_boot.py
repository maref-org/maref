"""PyInstaller boot entry point for MAREF Sidecar binary.

This script is the entry point for the packaged PyInstaller binary.
It mirrors the logic in maref_lite/cli.py:serve() but as a standalone
script so PyInstaller can trace all imports.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys


def _ensure_runtime_secrets() -> None:
    """Ensure runtime signing secrets exist so the binary is self-contained.

    AuditLogger and MCPGateway require signing keys that production would
    provide via environment variables. When unset, generate ephemeral secrets
    for this process (audit signatures and MCP HMACs are per-run only).
    """
    if "MAREF_ED25519_PRIVATE_KEY" not in os.environ and "MAREF_HMAC_SECRET_KEY" not in os.environ:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        os.environ["MAREF_ED25519_PRIVATE_KEY"] = Ed25519KeyPair.generate().private_key_pem
        print(
            "WARNING: No audit signing key configured (MAREF_ED25519_PRIVATE_KEY / "
            "MAREF_HMAC_SECRET_KEY). Generated an ephemeral Ed25519 key; audit "
            "signatures are per-run only.",
            file=sys.stderr,
        )
    if b"MAREF_MCP_SECRET_KEY" not in os.environb:
        # os.environb values cannot contain NUL bytes; base64 keeps it printable.
        os.environb[b"MAREF_MCP_SECRET_KEY"] = base64.urlsafe_b64encode(os.urandom(32))


def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF Sidecar")
    parser.add_argument("--port", type=int, default=8000, help="HTTP server port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind address")
    parser.add_argument("--gui", action="store_true", help="Enable GUI endpoints")
    parser.add_argument("--telemetry", action="store_true", help="Enable telemetry bridge")
    args = parser.parse_args()

    _ensure_runtime_secrets()

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
