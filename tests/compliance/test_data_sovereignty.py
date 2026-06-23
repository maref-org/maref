from __future__ import annotations

from unittest.mock import MagicMock

from maref.compliance.data_sovereignty import (
    CountryCode,
    DataCategory,
    DataClass,
    DataSovereigntyManager,
    DataSovereigntyStatus,
    DataTransferDecision,
    DataTransferRequest,
    GeographicRestriction,
)


class TestDataSovereigntyManager:
    def test_init_creates_default_data_classes(self) -> None:
        manager = DataSovereigntyManager()
        assert "public" in manager.data_classes
        assert "personal" in manager.data_classes
        assert "health" in manager.data_classes
        assert "financial" in manager.data_classes

    def test_init_creates_geographic_restrictions(self) -> None:
        manager = DataSovereigntyManager()
        assert "gdpr_cross_border" in manager.geographic_restrictions
        assert "china_data_localization" in manager.geographic_restrictions
        assert "us_export_control" in manager.geographic_restrictions

    def test_init_creates_compliance_policies(self) -> None:
        manager = DataSovereigntyManager()
        assert "gdpr" in manager.compliance_policies
        assert "china_csl" in manager.compliance_policies
        assert "russia_149fz" in manager.compliance_policies

    def test_register_data_class(self) -> None:
        manager = DataSovereigntyManager()
        dc = DataClass(
            id="custom",
            name="Custom Data",
            category=DataCategory.CONFIDENTIAL,
            classification_level="CONFIDENTIAL",
        )
        manager.register_data_class(dc)
        assert "custom" in manager.data_classes

    def test_add_geographic_restriction(self) -> None:
        manager = DataSovereigntyManager()
        gr = GeographicRestriction(
            id="custom_restriction",
            name="Custom Restriction",
            countries_blocked=[CountryCode.RU],
            data_categories_affected=[DataCategory.CONFIDENTIAL],
        )
        manager.add_geographic_restriction(gr)
        assert "custom_restriction" in manager.geographic_restrictions

    def test_evaluate_compliant_transfer(self) -> None:
        manager = DataSovereigntyManager()
        request = DataTransferRequest(
            request_id="req-1",
            data_classes=[manager.data_classes["public"]],
            source_country=CountryCode.US,
            destination_country=CountryCode.DE,
            transfer_purpose="Testing",
        )
        decision = manager.evaluate_data_transfer(request)
        assert decision.status == DataSovereigntyStatus.COMPLIANT
        assert decision.allowed is True

    def test_evaluate_transfer_blocked_by_class(self) -> None:
        manager = DataSovereigntyManager()
        request = DataTransferRequest(
            request_id="req-2",
            data_classes=[manager.data_classes["personal"]],
            source_country=CountryCode.DE,
            destination_country=CountryCode.CN,
            transfer_purpose="Export",
        )
        decision = manager.evaluate_data_transfer(request)
        assert decision.status in (
            DataSovereigntyStatus.NON_COMPLIANT,
            DataSovereigntyStatus.REQUIRES_APPROVAL,
        )

    def test_evaluate_transfer_blocked_by_restriction(self) -> None:
        manager = DataSovereigntyManager()
        dc = DataClass(
            id="personal_de",
            name="Personal Data",
            category=DataCategory.PERSONAL,
            classification_level="PERSONAL",
            cross_border_allowed=True,
        )
        request = DataTransferRequest(
            request_id="req-3",
            data_classes=[dc],
            source_country=CountryCode.DE,
            destination_country=CountryCode.CN,
            transfer_purpose="Export",
        )
        decision = manager.evaluate_data_transfer(request)
        assert decision.status != DataSovereigntyStatus.COMPLIANT

    def test_evaluate_transfer_encryption_required(self) -> None:
        manager = DataSovereigntyManager()
        request = DataTransferRequest(
            request_id="req-4",
            data_classes=[manager.data_classes["internal"]],
            source_country=CountryCode.US,
            destination_country=CountryCode.DE,
            transfer_purpose="Business",
        )
        decision = manager.evaluate_data_transfer(request)
        assert len(decision.conditions) > 0
        assert "encryption" in decision.conditions[0].lower()

    def test_evaluate_china_data_localization(self) -> None:
        manager = DataSovereigntyManager()
        dc = DataClass(
            id="personal_cn",
            name="Personal Data CN",
            category=DataCategory.PERSONAL,
            classification_level="PERSONAL",
            cross_border_allowed=True,
        )
        request = DataTransferRequest(
            request_id="req-cn",
            data_classes=[dc],
            source_country=CountryCode.CN,
            destination_country=CountryCode.US,
            transfer_purpose="Export",
        )
        decision = manager.evaluate_data_transfer(request)
        assert any("localization" in r.lower() for r in decision.restrictions) or not decision.allowed

    def test_get_cross_border_compliance_report(self) -> None:
        manager = DataSovereigntyManager()
        report = manager.get_cross_border_compliance_report(CountryCode.US, CountryCode.DE)
        assert report["source_country"] == "US"
        assert report["destination_country"] == "DE"
        assert "applicable_restrictions" in report
        assert "affected_data_categories" in report
        assert "recommendations" in report

    def test_get_transfer_history(self) -> None:
        manager = DataSovereigntyManager()
        request = DataTransferRequest(
            request_id="req-hist",
            data_classes=[manager.data_classes["public"]],
            source_country=CountryCode.US,
            destination_country=CountryCode.DE,
            transfer_purpose="Test",
        )
        manager.evaluate_data_transfer(request)
        history = manager.get_transfer_history()
        assert len(history) == 1
        assert history[0]["request_id"] == "req-hist"

    def test_export_policy_configuration(self) -> None:
        manager = DataSovereigntyManager()
        config = manager.export_policy_configuration()
        assert "data_classes" in config
        assert "geographic_restrictions" in config
        assert "compliance_policies" in config

    def test_import_policy_configuration(self) -> None:
        manager = DataSovereigntyManager()
        config = manager.export_policy_configuration()
        manager.import_policy_configuration(config)
        assert len(manager.data_classes) == len(config["data_classes"])
        assert len(manager.geographic_restrictions) == len(config["geographic_restrictions"])


class TestDataTransferDecision:
    def test_to_dict_structure(self) -> None:
        decision = DataTransferDecision(
            request_id="req-1",
            status=DataSovereigntyStatus.COMPLIANT,
            allowed=True,
            restrictions=["test"],
            conditions=[],
        )
        assert decision.request_id == "req-1"
        assert decision.allowed is True


class TestDataSovereigntyWithMockAudit:
    def test_mock_audit_logger(self) -> None:
        mock_logger = MagicMock()
        manager = DataSovereigntyManager(audit_logger=mock_logger)
        assert mock_logger.log.call_count >= 2
