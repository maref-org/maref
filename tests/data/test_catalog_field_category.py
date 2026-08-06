"""Tests for C1: field-level category metadata linkage (v0.51 W3-S1).

A DataSource carries per-field DataCategory so that a field→category→sanitize
rule mapping can be enforced downstream (C2).
"""

from __future__ import annotations

from maref.compliance.data_sovereignty import DataCategory
from maref.data.catalog import DataSource, DataSourceType, FieldSpec


def _catalog_with_sensitive_fields() -> DataSource:
    return DataSource(
        name="patient_records",
        data_type=DataSourceType.TABLE,
        owner="health-team",
        fields=(
            FieldSpec(name="patient_name", data_type="string", data_category=DataCategory.HEALTH),
            FieldSpec(name="phone", data_type="string", data_category=DataCategory.PERSONAL),
            FieldSpec(name="diagnosis", data_type="string", data_category=DataCategory.HEALTH),
            FieldSpec(name="age", data_type="integer", data_category=DataCategory.PUBLIC),
        ),
    )


def test_category_for_field_mapping() -> None:
    source = _catalog_with_sensitive_fields()
    assert source.category_for_field("phone") == DataCategory.PERSONAL
    assert source.category_for_field("diagnosis") == DataCategory.HEALTH
    assert source.category_for_field("age") == DataCategory.PUBLIC


def test_category_for_missing_field_raises() -> None:
    source = _catalog_with_sensitive_fields()
    try:
        source.category_for_field("nonexistent")
    except ValueError as exc:
        assert "nonexistent" in str(exc)
    else:
        raise AssertionError("missing field should raise ValueError")


def test_sensitive_fields_filtering() -> None:
    source = _catalog_with_sensitive_fields()
    sensitive = source.sensitive_fields()
    names = {f.name for f in sensitive}
    # HEALTH + PERSONAL 属于敏感，PUBLIC 排除
    assert names == {"patient_name", "phone", "diagnosis"}


def test_sensitive_fields_serialize_category() -> None:
    source = _catalog_with_sensitive_fields()
    d = source.to_dict()
    phone = next(f for f in d["fields"] if f["name"] == "phone")
    assert phone["data_category"] == "personal"
    diagnosis = next(f for f in d["fields"] if f["name"] == "diagnosis")
    assert diagnosis["data_category"] == "health"


def test_field_to_sanitize_rule_mapping_surface() -> None:
    """C1 字段→分类→消毒规则的贯通面：敏感字段可枚举出分类用于规则选择."""
    source = _catalog_with_sensitive_fields()
    rule_hints = {
        f.name: f.data_category for f in source.fields if f.data_category != DataCategory.PUBLIC
    }
    assert rule_hints == {
        "patient_name": DataCategory.HEALTH,
        "phone": DataCategory.PERSONAL,
        "diagnosis": DataCategory.HEALTH,
    }
