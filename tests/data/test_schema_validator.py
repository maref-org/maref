"""Tests for SchemaValidator (v0.51 W1-S3 / A3).

Covers field-level type/required/enum constraints and schema drift detection.
"""

from __future__ import annotations

from maref.data.catalog import DataSource, DataSourceType, FieldSpec
from maref.data.schema_validator import SchemaValidator


def _source_with_fields(
    fields: list[FieldSpec],
    name: str = "orders",
) -> DataSource:
    return DataSource(
        name=name,
        data_type=DataSourceType.TABLE,
        owner="data-team",
        fields=tuple(fields),
    )


def _record(record: dict[str, object]) -> dict[str, object]:
    return record


def test_valid_record_passes() -> None:
    fields = [
        FieldSpec(name="order_id", data_type="string", required=True),
        FieldSpec(name="amount", data_type="number", required=True),
        FieldSpec(name="status", data_type="string", enum=("new", "paid", "shipped")),
    ]
    validator = SchemaValidator(fields)
    result = validator.validate_record(
        _record({"order_id": "ORD-1", "amount": 12.5, "status": "paid"})
    )
    assert result.valid
    assert result.errors == []


def test_missing_required_field_fails() -> None:
    fields = [FieldSpec(name="order_id", data_type="string", required=True)]
    validator = SchemaValidator(fields)
    result = validator.validate_record(_record({}))
    assert not result.valid
    assert any("order_id" in e for e in result.errors)


def test_wrong_type_fails() -> None:
    fields = [FieldSpec(name="amount", data_type="number", required=True)]
    validator = SchemaValidator(fields)
    result = validator.validate_record(_record({"amount": "not-a-number"}))
    assert not result.valid
    assert any("amount" in e for e in result.errors)


def test_enum_violation_fails() -> None:
    fields = [FieldSpec(name="status", data_type="string", enum=("new", "paid"))]
    validator = SchemaValidator(fields)
    result = validator.validate_record(_record({"status": "cancelled"}))
    assert not result.valid
    assert any("status" in e for e in result.errors)


def test_unknown_field_reported_but_not_fatal() -> None:
    fields = [FieldSpec(name="id", data_type="string")]
    validator = SchemaValidator(fields)
    result = validator.validate_record(_record({"id": "x", "extra": 1}))
    # 未知字段被记录但整体仍有效（宽容策略）
    assert result.valid
    assert any("extra" in e for e in result.warnings)


def test_detect_schema_drift_type_change() -> None:
    old = [FieldSpec(name="amount", data_type="string")]
    new = [FieldSpec(name="amount", data_type="number")]
    drift = SchemaValidator.detect_schema_drift(old, new)
    assert any("amount" in d and "number" in d for d in drift)
    assert len(drift) >= 1


def test_detect_schema_drift_added_required_field() -> None:
    old = [FieldSpec(name="id", data_type="string", required=True)]
    new = [
        FieldSpec(name="id", data_type="string", required=True),
        FieldSpec(name="region", data_type="string", required=True),
    ]
    drift = SchemaValidator.detect_schema_drift(old, new)
    assert any("region" in d for d in drift)


def test_detect_schema_drift_enum_narrowing() -> None:
    old = [FieldSpec(name="status", data_type="string", enum=("a", "b", "c"))]
    new = [FieldSpec(name="status", data_type="string", enum=("a",))]

    drift = SchemaValidator.detect_schema_drift(old, new)
    assert any("status" in d for d in drift)


def test_none_required_field_fails() -> None:
    fields = [FieldSpec(name="id", data_type="string", required=True)]
    validator = SchemaValidator(fields)
    result = validator.validate_record({"id": None})
    assert not result.valid
    assert any("id" in e for e in result.errors)


def test_none_optional_field_passes() -> None:
    fields = [FieldSpec(name="note", data_type="string")]
    validator = SchemaValidator(fields)
    result = validator.validate_record({"note": None})
    assert result.valid


def test_boolean_and_timestamp_types() -> None:
    fields = [
        FieldSpec(name="active", data_type="boolean"),
        FieldSpec(name="created", data_type="timestamp"),
        FieldSpec(name="unknown_type", data_type="json"),
    ]
    validator = SchemaValidator(fields)
    result = validator.validate_record(
        {"active": True, "created": "2026-08-04", "unknown_type": {"a": 1}}
    )
    assert result.valid


def test_boolean_rejects_string() -> None:
    fields = [FieldSpec(name="active", data_type="boolean")]
    validator = SchemaValidator(fields)
    result = validator.validate_record({"active": "yes"})
    assert not result.valid


def test_detect_schema_drift_removed_field() -> None:
    old = [FieldSpec(name="legacy", data_type="string"), FieldSpec(name="keep", data_type="string")]
    new = [FieldSpec(name="keep", data_type="string")]
    drift = SchemaValidator.detect_schema_drift(old, new)
    assert any("legacy" in d for d in drift)


def test_fingerprint_stable_and_sensitive_to_change() -> None:
    fields_a = [FieldSpec(name="id", data_type="string", required=True)]
    fields_b = [FieldSpec(name="id", data_type="string", required=True)]
    fields_c = [FieldSpec(name="id", data_type="integer", required=True)]
    assert SchemaValidator.fingerprint(fields_a) == SchemaValidator.fingerprint(fields_b)
    assert SchemaValidator.fingerprint(fields_a) != SchemaValidator.fingerprint(fields_c)
    assert SchemaValidator.fingerprint(fields_a).startswith("sha256:")
