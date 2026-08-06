#!/usr/bin/env python3
"""Phase 2.1 SchemaRegistry + SchemaAligner tests."""

from __future__ import annotations

from maref.recursive.schema_aligner import (
    FieldMapping,
    SchemaAligner,
    SchemaRegistry,
    SchemaVersion,
)


def test_registry_versioning():
    reg = SchemaRegistry()
    reg.register(
        SchemaVersion(
            schema_id="analysis_input",
            version="1.0.0",
            fields={"query": "string", "depth": "integer"},
            required=["query"],
        )
    )
    reg.register(
        SchemaVersion(
            schema_id="analysis_input",
            version="2.0.0",
            fields={"query": "string", "depth": "integer", "format": "string"},
            required=["query", "format"],
        )
    )

    v1 = reg.get("analysis_input", "1.0.0")
    assert v1 is not None
    assert "format" not in v1.fields

    latest = reg.get("analysis_input", "latest")
    assert latest is not None
    assert "format" in latest.fields
    print("  registry_versioning OK")


def test_compatibility_score():
    reg = SchemaRegistry()
    reg.register(
        SchemaVersion(
            schema_id="schema_a",
            version="1.0.0",
            fields={"x": "string", "y": "integer"},
            required=["x", "y"],
        )
    )
    reg.register(
        SchemaVersion(
            schema_id="schema_b",
            version="1.0.0",
            fields={"x": "string", "z": "boolean"},
            required=["x", "z"],
        )
    )

    score = reg.compatibility_score("schema_a", "schema_b")
    # shared required = {x}, union = {x, y, z} -> 1/3
    assert abs(score - 1 / 3) < 0.01
    print("  compatibility_score OK")


def test_align_identity():
    aligner = SchemaAligner()
    aligner.register_mapping(
        "schema_a",
        "schema_b",
        [
            FieldMapping("name", "agent_name"),
            FieldMapping("age", "agent_age"),
        ],
    )
    result = aligner.align(
        {"name": "Alice", "age": 30},
        "schema_a",
        "schema_b",
    )
    assert result.success
    assert result.mapped_data == {"agent_name": "Alice", "agent_age": 30}
    print("  align_identity OK")


def test_align_with_transform():
    aligner = SchemaAligner()
    aligner.register_mapping(
        "schema_a",
        "schema_b",
        [
            FieldMapping("tags", "tag_string", transform="concat:, "),
        ],
    )
    result = aligner.align(
        {"tags": ["fast", "reliable"]},
        "schema_a",
        "schema_b",
    )
    assert result.success
    assert result.mapped_data["tag_string"] == "fast, reliable"
    print("  align_with_transform OK")


def test_align_missing_required():
    aligner = SchemaAligner()
    aligner.register_mapping(
        "schema_a",
        "schema_b",
        [
            FieldMapping("required_field", "target_required"),
        ],
    )
    result = aligner.align(
        {},
        "schema_a",
        "schema_b",
    )
    assert not result.success
    assert "target_required" in result.missing_required
    print("  align_missing_required OK")


def test_align_detects_extra_fields():
    aligner = SchemaAligner()
    aligner.register_mapping(
        "schema_a",
        "schema_b",
        [
            FieldMapping("known", "known_out"),
        ],
    )
    result = aligner.align(
        {"known": 1, "extra": 2},
        "schema_a",
        "schema_b",
    )
    assert "extra" in result.extra_fields
    print("  align_detects_extra_fields OK")


def test_can_align_with_registry():
    reg = SchemaRegistry()
    reg.register(
        SchemaVersion(
            schema_id="s1",
            version="1.0.0",
            fields={"a": "string"},
            required=["a"],
        )
    )
    reg.register(
        SchemaVersion(
            schema_id="s2",
            version="1.0.0",
            fields={"a": "string"},
            required=["a"],
        )
    )
    aligner = SchemaAligner(registry=reg)
    assert aligner.can_align("s1", "s2")
    print("  can_align_with_registry OK")


if __name__ == "__main__":
    test_registry_versioning()
    test_compatibility_score()
    test_align_identity()
    test_align_with_transform()
    test_align_missing_required()
    test_align_detects_extra_fields()
    test_can_align_with_registry()
    print("All Phase 2 Schema tests passed")
