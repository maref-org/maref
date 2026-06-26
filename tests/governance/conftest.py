"""Pytest fixtures for governance tests."""

from __future__ import annotations

import os

# FederatedAudit requires this key for HMAC operations.
# In tests, use a fixed test key.
os.environ.setdefault("MAREF_FEDERATED_AUDIT_KEY", "test-key-for-unit-tests-only")
