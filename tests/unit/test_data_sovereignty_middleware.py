"""Data sovereignty middleware + compliance engine enforcement tests.

Validates P0-2: compliance moves from "declarative" to "enforced".
- DataSovereigntyMiddleware intercepts cross-border data transfers in the
  MCP request chain (blocks non-compliant, allows compliant, backward compat).
- ComplianceEngine.evaluate_compliance rejects placeholder evidence.
"""

from __future__ import annotations

import os

import pytest

from maref.compliance.data_sovereignty import DataSovereigntyManager
from maref.compliance.registry import (
    ComplianceEngine,
    ComplianceRegistry,
    ComplianceRequirement,
    ComplianceStatus,
    Jurisdiction,
)
from maref.integration.mcp_security_middleware import (
    DataSovereigntyMiddleware,
    MCPSecurityMiddleware,
)
from maref.integration.mcp_transport import JSONRPCRequest


@pytest.fixture(autouse=True)
def _set_hmac_secret() -> None:
    os.environ["MAREF_HMAC_SECRET_KEY"] = "test-sovereignty-secret"
    yield
    os.environ.pop("MAREF_HMAC_SECRET_KEY", None)


def _request(params: dict | None = None) -> JSONRPCRequest:
    return JSONRPCRequest(jsonrpc="2.0", method="tools/call", params=params, id=1)


# ------------------------------------------------------------------
# DataSovereigntyMiddleware
# ------------------------------------------------------------------


class TestDataSovereigntyMiddleware:
    def test_no_manager_allows_all(self) -> None:
        mw = DataSovereigntyMiddleware(None)
        result = mw.process(_request({"data_transfer": {"source_country": "CN"}}))
        assert result.is_allowed is True

    def test_no_data_transfer_field_allows(self) -> None:
        mw = DataSovereigntyMiddleware(DataSovereigntyManager())
        result = mw.process(_request({"tool": "file.read"}))
        assert result.is_allowed is True

    def test_invalid_context_denied(self) -> None:
        mw = DataSovereigntyMiddleware(DataSovereigntyManager())
        result = mw.process(_request({"data_transfer": {"source_country": "CN"}}))
        assert result.is_allowed is False
        assert "invalid data_transfer" in result.reason

    def test_confidential_cross_border_denied(self) -> None:
        mw = DataSovereigntyMiddleware(DataSovereigntyManager())
        result = mw.process(
            _request(
                {
                    "data_transfer": {
                        "source_country": "CN",
                        "destination_country": "BR",
                        "data_class_ids": ["confidential"],
                        "purpose": "sharing",
                    }
                }
            )
        )
        assert result.is_allowed is False
        assert "data sovereignty" in result.reason

    def test_public_cross_border_allowed(self) -> None:
        mw = DataSovereigntyMiddleware(DataSovereigntyManager())
        result = mw.process(
            _request(
                {
                    "data_transfer": {
                        "source_country": "CN",
                        "destination_country": "US",
                        "data_class_ids": ["public"],
                        "purpose": "publish",
                    }
                }
            )
        )
        assert result.is_allowed is True


# ------------------------------------------------------------------
# MCPSecurityMiddleware integration
# ------------------------------------------------------------------


class TestMCPSecurityMiddlewareIntegration:
    def test_sovereignty_integration_blocks(self) -> None:
        mgr = DataSovereigntyManager()
        mw = MCPSecurityMiddleware(data_sovereignty_manager=mgr)
        result = mw.process(
            _request(
                {
                    "name": "file.write",
                    "arguments": {},
                    "data_transfer": {
                        "source_country": "CN",
                        "destination_country": "BR",
                        "data_class_ids": ["confidential"],
                    },
                }
            )
        )
        assert result.is_allowed is False
        assert result.verdict == "DENY"
        assert "data sovereignty" in result.reason

    def test_no_sovereignty_manager_backward_compat(self) -> None:
        mw = MCPSecurityMiddleware()
        result = mw.process(_request({"name": "file.read", "arguments": {}}))
        assert result.is_allowed is True


# ------------------------------------------------------------------
# ComplianceEngine evidence validation
# ------------------------------------------------------------------


class TestComplianceEngineEvidenceValidation:
    @staticmethod
    def _make_registry() -> ComplianceRegistry:
        registry = ComplianceRegistry()
        registry.requirements["req-1"] = ComplianceRequirement(
            requirement_id="req-1",
            regulation_id="gdpr",
            name="Lawful Basis",
            description="Process data with lawful basis",
            jurisdiction=Jurisdiction.EU,
        )
        return registry

    def test_valid_evidence_compliant(self) -> None:
        engine = ComplianceEngine(self._make_registry())
        result = engine.evaluate_compliance("req-1", ["consent.pdf", "dpia.docx"])
        assert result.status == ComplianceStatus.COMPLIANT
        assert result.score == 100.0

    def test_placeholder_evidence_non_compliant(self) -> None:
        engine = ComplianceEngine(self._make_registry())
        result = engine.evaluate_compliance("req-1", ["n/a", "", "todo", "TBD"])
        assert result.status == ComplianceStatus.NON_COMPLIANT
        assert result.score == 0.0
        assert "placeholders rejected" in result.findings[0]

    def test_empty_evidence_non_compliant(self) -> None:
        engine = ComplianceEngine(self._make_registry())
        result = engine.evaluate_compliance("req-1", [])
        assert result.status == ComplianceStatus.NON_COMPLIANT
