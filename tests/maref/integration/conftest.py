"""Conftest for maref.integration tests.

An earlier version of this file injected ``MagicMock`` stubs for
``maref.integration.*`` sub-modules into ``sys.modules`` to work around a
circular-import chain that no longer exists. Those stubs leaked into every
other test module collected afterwards (breaking ``tests/unit/test_aip_adapter``
and ``tests/unit/test_sidecar_server_extended``), so they were removed.

Verified: ``import maref.integration`` succeeds without stubs and all
integration tests here pass with real modules.
"""
