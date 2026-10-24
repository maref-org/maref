import os
os.environ.setdefault("MAREF_HMAC_SECRET_KEY", "test_key")
os.environ.setdefault("MAREF_MCP_SECRET_KEY", "test_key")
os.environ.setdefault("MAREF_TELEMETRY_HMAC_KEY", "test_key")
os.environ.setdefault("MAREF_ALLOW_UNAUTHENTICATED", "1")

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from maref.obs import MarefObsClient
from sidecar.obs_bridge import ObsBridge
from sidecar.server import create_app

def create_test_app():
    return create_app(
        ObservationCollector(adapter=MockAgentAdapter()),
        CompositeMonitor(),
        obs_bridge=None,
        allow_unauthenticated=True
    )
