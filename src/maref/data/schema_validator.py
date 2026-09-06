"""SchemaValidator: field-level schema validation and drift detection.

Validates records against a declared :class:`FieldSpec` set (type / required /
enum) and detects schema drift between schema versions. Bridges to
:mod:`maref.recursive.schema_aligner` for compatibility scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maref.data.catalog import FieldSpec

_NUMERIC_TYPES = {"number", "integer", "float"}
_STRING_TYPES = {"string", "text", "varchar"}


@dataclass
class ValidationResult:
    """Outcome of a single record validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SchemaValidator:
    """Validates records against a declared field schema."""

    def __init__(self, fields: list[FieldSpec]) -> None:
        self._fields = {f.name: f for f in fields}

    @property
    def field_names(self) -> set[str]:
        return set(self._fields)

    def validate_record(self, record: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        for name, spec in self._fields.items():
            if name not in record:
                if spec.required:
                    errors.append(f"missing required field: {name}")
                continue
            value = record[name]
            if value is None:
                if spec.required:
                    errors.append(f"required field {name} is None")
                continue
            if not self._type_ok(spec.data_type, value):
                errors.append(
                    f"field {name} has type {type(value).__name__}, expected {spec.data_type}"
                )
            if spec.enum and value not in spec.enum:
                errors.append(f"field {name} value {value!r} not in enum {list(spec.enum)}")

        for name in record:
            if name not in self._fields:
                warnings.append(f"unknown field: {name}")

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    @staticmethod
    def _type_ok(declared: str, value: Any) -> bool:
        if declared in _NUMERIC_TYPES:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if declared in _STRING_TYPES:
            return isinstance(value, str)
        if declared == "boolean":
            return isinstance(value, bool)
        if declared in ("timestamp", "datetime"):
            return isinstance(value, str)
        return True  # unknown declared types default to lenient

    @staticmethod
    def detect_schema_drift(old: list[FieldSpec], new: list[FieldSpec]) -> list[str]:
        """Return human-readable drift descriptions between two schemas."""
        drift: list[str] = []
        old_map = {f.name: f for f in old}
        new_map = {f.name: f for f in new}

        for name, new_spec in new_map.items():
            old_spec = old_map.get(name)
            if old_spec is None:
                drift.append(f"field added: {name}")
                continue
            if old_spec.data_type != new_spec.data_type:
                drift.append(
                    f"field {name} type changed: {old_spec.data_type} -> {new_spec.data_type}"
                )
            if new_spec.required and not old_spec.required:
                drift.append(f"field {name} became required")
            if old_spec.enum and new_spec.enum and set(new_spec.enum) < set(old_spec.enum):
                drift.append(
                    f"field {name} enum narrowed: {list(old_spec.enum)} -> {list(new_spec.enum)}"
                )

        for name in old_map:
            if name not in new_map:
                drift.append(f"field removed: {name}")

        return drift

    @staticmethod
    def fingerprint(fields: list[FieldSpec]) -> str:
        """Stable schema fingerprint for change detection.

        Includes each field's data_category so a PUBLIC→HEALTH reclassification
        (the key governance event in C1) changes the fingerprint (I4 fix).
        """
        import hashlib

        canonical = "|".join(
            f"{f.name}:{f.data_type}:{f.data_category.value}:"
            f"{'r' if f.required else 'o'}:{','.join(sorted(f.enum))}"
            for f in sorted(fields, key=lambda f: f.name)
        )
        return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"
