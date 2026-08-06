"""Smoke tests for maref.recursive.schema_aligner."""
from __future__ import annotations

import pytest

from maref.recursive.schema_aligner import (
    AlignmentResult,
    FieldMapping,
    SchemaAligner,
    SchemaRegistry,
    SchemaVersion,
)


class TestFieldMapping:
    def test_init_default(self) -> None:
        mapping = FieldMapping(source_field="name", target_field="full_name")
        assert mapping.source_field == "name"
        assert mapping.target_field == "full_name"
        assert mapping.transform == "identity"
        assert mapping.required is True

    def test_init_custom(self) -> None:
        mapping = FieldMapping(
            source_field="first", target_field="last",
            transform="uppercase", required=False,
        )
        assert mapping.transform == "uppercase"
        assert mapping.required is False

    def test_to_dict(self) -> None:
        mapping = FieldMapping(source_field="a", target_field="b")
        d = mapping.to_dict()
        assert d["source_field"] == "a"
        assert d["transform"] == "identity"


class TestSchemaVersion:
    def test_init_default(self) -> None:
        schema = SchemaVersion(schema_id="user", version="1.0")
        assert schema.schema_id == "user"
        assert schema.version == "1.0"
        assert schema.fields == {}
        assert schema.required == []

    def test_init_custom(self) -> None:
        schema = SchemaVersion(
            schema_id="user", version="2.0",
            fields={"name": "str", "age": "int"},
            required=["name"], description="User schema v2",
        )
        assert schema.fields == {"name": "str", "age": "int"}
        assert schema.description == "User schema v2"

    def test_to_dict(self) -> None:
        schema = SchemaVersion(schema_id="user", version="1.0")
        d = schema.to_dict()
        assert d["schema_id"] == "user"
        assert d["version"] == "1.0"


class TestSchemaRegistry:
    def test_init(self) -> None:
        registry = SchemaRegistry()
        assert registry is not None

    def test_register_and_get(self) -> None:
        registry = SchemaRegistry()
        schema = SchemaVersion(schema_id="user", version="1.0", fields={"name": "str"})
        registry.register(schema)
        result = registry.get("user", "1.0")
        assert result is not None
        assert result.schema_id == "user"
        assert result.fields == {"name": "str"}

    def test_get_nonexistent(self) -> None:
        registry = SchemaRegistry()
        assert registry.get("nonexistent") is None

    def test_get_latest(self) -> None:
        registry = SchemaRegistry()
        registry.register(SchemaVersion(schema_id="user", version="1.0", fields={"name": "str"}))
        registry.register(SchemaVersion(schema_id="user", version="2.0", fields={"name": "str", "age": "int"}))
        latest = registry.get("user")
        assert latest is not None
        assert latest.version == "2.0"

    def test_list_versions(self) -> None:
        registry = SchemaRegistry()
        registry.register(SchemaVersion(schema_id="user", version="1.0"))
        registry.register(SchemaVersion(schema_id="user", version="2.0"))
        versions = registry.list_versions("user")
        assert "1.0" in versions
        assert "2.0" in versions
        assert registry.list_versions("nonexistent") == []

    def test_compatibility_score(self) -> None:
        registry = SchemaRegistry()
        registry.register(SchemaVersion(schema_id="a", version="1.0", required=["x", "y"]))
        registry.register(SchemaVersion(schema_id="b", version="1.0", required=["x", "z"]))
        score = registry.compatibility_score("a", "b")
        assert score == 1.0 / 3.0

    def test_compatibility_score_nonexistent(self) -> None:
        registry = SchemaRegistry()
        assert registry.compatibility_score("a", "nonexistent") == 0.0


class TestAlignmentResult:
    def test_init_default(self) -> None:
        result = AlignmentResult(success=True)
        assert result.success is True
        assert result.mapped_data == {}
        assert result.missing_required == []
        assert result.errors == []

    def test_init_custom(self) -> None:
        result = AlignmentResult(
            success=False, mapped_data={"name": "Alice"},
            missing_required=["age"], errors=["transform error"],
        )
        assert result.success is False
        assert result.mapped_data == {"name": "Alice"}

    def test_to_dict(self) -> None:
        result = AlignmentResult(success=True)
        d = result.to_dict()
        assert d["success"] is True


class TestSchemaAligner:
    def test_init_default(self) -> None:
        aligner = SchemaAligner()
        assert aligner is not None
        assert aligner._mappings == {}

    def test_init_with_registry(self) -> None:
        registry = SchemaRegistry()
        aligner = SchemaAligner(registry=registry)
        assert aligner is not None

    def test_register_mapping(self) -> None:
        aligner = SchemaAligner()
        mapping = FieldMapping(source_field="name", target_field="full_name")
        aligner.register_mapping("src", "tgt", [mapping])
        assert len(aligner._mappings) == 1

    def test_align_simple(self) -> None:
        aligner = SchemaAligner()
        aligner.register_mapping(
            "src", "tgt",
            [FieldMapping(source_field="name", target_field="full_name")],
        )
        result = aligner.align({"name": "Alice"}, "src", "tgt")
        assert result.success is True
        assert result.mapped_data.get("full_name") == "Alice"

    def test_align_empty_data(self) -> None:
        aligner = SchemaAligner()
        result = aligner.align({}, "src", "tgt")
        assert result.success is True
        assert result.mapped_data == {}

    def test_align_missing_required(self) -> None:
        aligner = SchemaAligner()
        aligner.register_mapping(
            "src", "tgt",
            [FieldMapping(source_field="name", target_field="full_name")],
        )
        result = aligner.align({}, "src", "tgt")
        assert result.success is False
        assert "full_name" in result.missing_required

    def test_can_align(self) -> None:
        aligner = SchemaAligner()
        assert aligner.can_align("src", "tgt") is False
        aligner.register_mapping(
            "src", "tgt",
            [FieldMapping(source_field="name", target_field="full_name")],
        )
        assert aligner.can_align("src", "tgt") is True
