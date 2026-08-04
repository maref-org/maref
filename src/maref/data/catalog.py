"""DataCatalog: enterprise data source registration and governance.

Provides:
- DataSource: registered enterprise data asset with classification metadata
- DataCatalog: register / lookup / ownership filtering / change notifications

This is the onboarding gate of the enterprise value flywheel (v0.51 W1-S1 / A1):
an enterprise data source cannot feed knowledge without being cataloged,
classified, and subject to schema validation.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.compliance.data_sovereignty import DataCategory


class DataSourceType(Enum):
    """Physical shape of an enterprise data source."""

    TABLE = "table"
    FILE = "file"
    STREAM = "stream"
    API = "api"
    DATABASE = "database"


@dataclass(frozen=True)
class FieldSpec:
    """Field-level metadata; carries the field→category mapping (C1)."""

    name: str
    data_type: str = "string"
    required: bool = False
    enum: tuple[str, ...] = ()
    data_category: DataCategory = DataCategory.PUBLIC

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "required": self.required,
            "enum": list(self.enum),
            "data_category": self.data_category.value,
        }


@dataclass(frozen=True)
class DataSource:
    """A registered enterprise data asset."""

    name: str
    data_type: DataSourceType
    owner: str
    categories: tuple[DataCategory, ...] = (DataCategory.PUBLIC,)
    sensitive_tags: frozenset[str] = frozenset()
    schema_fingerprint: str = ""
    dataset_id: str = field(default_factory=lambda: f"ds-{uuid.uuid4().hex[:12]}")
    created_at: float = field(default_factory=time.time)
    fields: tuple[FieldSpec, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "data_type": self.data_type.value,
            "owner": self.owner,
            "categories": [c.value for c in self.categories],
            "sensitive_tags": set(self.sensitive_tags),
            "schema_fingerprint": self.schema_fingerprint,
            "created_at": self.created_at,
            "fields": [f.to_dict() for f in self.fields],
        }

    def category_for_field(self, field_name: str) -> DataCategory:
        """Return the DataCategory declared for a field (C1 field-level mapping)."""
        for f in self.fields:
            if f.name == field_name:
                return f.data_category
        raise ValueError(f"field {field_name!r} not present in data source {self.name!r}")

    def sensitive_fields(self) -> tuple[FieldSpec, ...]:
        """Return fields whose category is not PUBLIC (need classification-aware sanitization)."""
        return tuple(f for f in self.fields if f.data_category != DataCategory.PUBLIC)


ChangeCallback = Callable[[DataSource], None]
RemovalCallback = Callable[[str], None]


class DataCatalog:
    """In-memory catalog of registered enterprise data sources."""

    def __init__(self) -> None:
        self._sources: dict[str, DataSource] = {}
        self._by_name: dict[str, str] = {}
        self._on_register: list[ChangeCallback] = []
        self._on_removal: list[RemovalCallback] = []

    def subscribe(self, callback: ChangeCallback) -> None:
        self._on_register.append(callback)

    def subscribe_removal(self, callback: RemovalCallback) -> None:
        self._on_removal.append(callback)

    def register(self, source: DataSource) -> str:
        if source.name in self._by_name:
            raise ValueError(f"data source {source.name!r} already registered")
        self._sources[source.dataset_id] = source
        self._by_name[source.name] = source.dataset_id
        for cb in self._on_register:
            cb(source)
        return source.dataset_id

    def unregister(self, dataset_id: str) -> None:
        source = self._sources.pop(dataset_id, None)
        if source is None:
            return
        self._by_name.pop(source.name, None)
        for cb in self._on_removal:
            cb(dataset_id)

    def get(self, dataset_id: str) -> DataSource | None:
        return self._sources.get(dataset_id)

    def get_by_name(self, name: str) -> DataSource | None:
        dataset_id = self._by_name.get(name)
        return self._sources.get(dataset_id) if dataset_id else None

    def list_by_owner(self, owner: str) -> list[DataSource]:
        return [s for s in self._sources.values() if s.owner == owner]

    def all(self) -> list[DataSource]:
        return list(self._sources.values())
