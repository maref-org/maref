"""Conftest: no module-level stubs.

Historically this file injected ``MagicMock`` stubs for
``maref.integration`` sub-modules into ``sys.modules`` to dodge a circular
import chain (governance -> recursive -> evolution). That stub logic polluted
the global ``sys.modules`` for the entire pytest run, so unit tests that import
the real modules (``test_aip_adapter``, ``test_mcp_hitl_bridge``,
``test_a2a_bridge``, ``test_maref_loop_adapter``, ...) received a MagicMock and
failed — sonarcloud reported 74 failures from exactly this.

The circular import is no longer reachable: ``import maref.integration`` works
directly, so the stubs were removed (2026-08-14).
"""
