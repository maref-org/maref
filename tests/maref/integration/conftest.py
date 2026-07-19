"""Conftest: prevent circular imports when importing maref.integration modules.

maref.integration's __init__.py eagerly imports many sub-modules, some of which
(e.g. a2a_bridge, deerflow_bridge) import from maref.governance.*, triggering
a circular import chain (governance -> recursive -> evolution -> governance).

We stub the integration sub-modules that carry governance imports so they're
already in sys.modules — their real code runs only when individually imported.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Only stub integration sub-modules that trigger governance imports.
# The top-level maref.governance package and its sub-modules are NOT stubbed
# so they remain usable by other test suites.
_STUB_MODULES = [
    "maref.integration.a2a_bridge",
    "maref.integration.a2a_types",
    "maref.integration.a2a_client",
    "maref.integration.a2a_discovery",
    "maref.integration.a2a_secure_transport",
    "maref.integration.a2a_server",
    "maref.integration.deerflow_bridge",
    "maref.integration.flag_bridge",
    "maref.integration.gateway",
    "maref.integration.hitl",
    "maref.integration.maref_loop_adapter",
    "maref.integration.mcp_governance",
    "maref.integration.memory_bridge",
    "maref.integration.remote_bridge",
    "maref.integration.symphony",
    "maref.integration.trajectory",
    "maref.integration.percv",
    "maref.integration.percv.pipeline_adapter",
    "maref.integration.percv.gateway_adapter",
    "maref.integration.percv.orchestrator",
    "maref.integration.percv.cost_monitor",
    "maref.integration.aip_adapter",
    "maref.integration.test_platform",
    "maref.integration.test_platform.tla_verifier",
    "maref.integration.test_platform.state_trigger",
    "maref.integration.test_platform.eval_observer",
    "maref.integration.feature_dev.feature_cycle",
]

for mod_name in _STUB_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
