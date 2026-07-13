from __future__ import annotations

from datetime import datetime

from maref.compliance.data_sovereignty import (
    CountryCode,
    DataCategory,
    DataClass,
    DataFlowDirection,
    DataSovereigntyManager,
    DataSovereigntyStatus,
    DataTransferDecision,
    DataTransferRequest,
    GeographicRestriction,
)


class TestDataCategory:
    def test_values(self) -> None:
        assert DataCategory.PUBLIC.value == "public"
        assert DataCategory.INTERNAL.value == "internal"
        assert DataCategory.CONFIDENTIAL.value == "confidential"
        assert DataCategory.RESTRICTED.value == "restricted"
        assert DataCategory.PERSONAL.value == "personal"
        assert DataCategory.SENSITIVE_PERSONAL.value == "sensitive_personal"
        assert DataCategory.HEALTH.value == "health"
        assert DataCategory.FINANCIAL.value == "financial"
        assert DataCategory.CRITICAL_INFRASTRUCTURE.value == "critical_infrastructure"

    def test_members(self) -> None:
        assert len(DataCategory) == 9


class TestDataFlowDirection:
    def test_values(self) -> None:
        assert DataFlowDirection.INBOUND.value == "inbound"
        assert DataFlowDirection.OUTBOUND.value == "outbound"
        assert DataFlowDirection.INTERNAL.value == "internal"
        assert DataFlowDirection.CROSS_BORDER.value == "cross_border"


class TestCountryCode:
    def test_values(self) -> None:
        assert CountryCode.US.value == "US"
        assert CountryCode.CN.value == "CN"
        assert CountryCode.DE.value == "DE"

    def test_members(self) -> None:
        assert len(CountryCode) == 13


class TestDataSovereigntyStatus:
    def test_values(self) -> None:
        assert DataSovereigntyStatus.COMPLIANT.value == "compliant"
        assert DataSovereigntyStatus.BLOCKED.value == "blocked"


class TestDataClass:
    def test_defaults(self) -> None:
        dc = DataClass(
            id="dc1",
            name="Customer Data",
            category=DataCategory.PERSONAL,
            classification_level="L3",
        )
        assert dc.id == "dc1"
        assert dc.category == DataCategory.PERSONAL
        assert dc.protection_requirements == []
        assert dc.encryption_required is False
        assert dc.cross_border_allowed is True

    def test_custom(self) -> None:
        dc = DataClass(
            id="dc2",
            name="Financial Records",
            category=DataCategory.FINANCIAL,
            classification_level="L5",
            encryption_required=True,
            cross_border_allowed=False,
            allowed_jurisdictions=["CN"],
        )
        assert dc.encryption_required is True
        assert dc.cross_border_allowed is False


class TestGeographicRestriction:
    def test_defaults(self) -> None:
        gr = GeographicRestriction(id="gr1", name="China Only")
        assert gr.countries_allowed == []
        assert gr.countries_blocked == []
        assert gr.requires_approval is False

    def test_with_values(self) -> None:
        gr = GeographicRestriction(
            id="gr2",
            name="Block US",
            countries_blocked=[CountryCode.US],
            data_categories_affected=[DataCategory.PERSONAL],
            requires_approval=True,
        )
        assert CountryCode.US in gr.countries_blocked
        assert gr.requires_approval is True


class TestDataTransferRequest:
    def test_defaults(self) -> None:
        dc = DataClass(id="dc1", name="Test", category=DataCategory.PUBLIC, classification_level="L1")
        req = DataTransferRequest(
            request_id="r1",
            data_classes=[dc],
            source_country=CountryCode.CN,
            destination_country=CountryCode.US,
            transfer_purpose="backup",
        )
        assert req.request_id == "r1"
        assert req.encrypted is False
        assert req.data_volume_kb is None


class TestDataTransferDecision:
    def test_defaults(self) -> None:
        dec = DataTransferDecision(
            request_id="r1",
            status=DataSovereigntyStatus.COMPLIANT,
            allowed=True,
        )
        assert dec.allowed is True
        assert dec.restrictions == []
        assert dec.approval_required is False


class TestDataSovereigntyManager:
    def test_init(self) -> None:
        mgr = DataSovereigntyManager()
        # init populates default data classes and restrictions
        assert len(mgr.data_classes) >= 1
        assert mgr.transfer_history == []
        assert "gdpr" in mgr.compliance_policies
        assert "china_csl" in mgr.compliance_policies
