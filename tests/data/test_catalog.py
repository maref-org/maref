"""Tests for DataCatalog (v0.51 W1-S1 / A1).

Covers data source registration, lookup, ownership filtering, and change
notification events required for enterprise data onboarding governance.
"""

from __future__ import annotations

from maref.compliance.data_sovereignty import DataCategory
from maref.data.catalog import DataCatalog, DataSource, DataSourceType


def _sample_source(
    name: str = "customer_master",
    owner: str = "data-platform-team",
    data_type: DataSourceType = DataSourceType.TABLE,
    categories: tuple[DataCategory, ...] = (DataCategory.PERSONAL,),
) -> DataSource:
    return DataSource(
        name=name,
        data_type=data_type,
        owner=owner,
        categories=categories,
        sensitive_tags={"pii"},
        schema_fingerprint="sha256:abc123",
    )


def test_datasource_defaults_and_serialization() -> None:
    source = _sample_source()
    assert source.dataset_id.startswith("ds-")
    assert source.created_at > 0
    d = source.to_dict()
    assert d["name"] == "customer_master"
    assert d["data_type"] == "table"
    assert d["categories"] == ["personal"]
    assert d["sensitive_tags"] == {"pii"}


def test_register_and_lookup() -> None:
    catalog = DataCatalog()
    source = _sample_source()
    dataset_id = catalog.register(source)
    assert dataset_id == source.dataset_id
    assert catalog.get(dataset_id) == source


def test_register_duplicate_name_raises() -> None:
    catalog = DataCatalog()
    catalog.register(_sample_source(name="dup"))
    try:
        catalog.register(_sample_source(name="dup"))
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate registration should raise ValueError")


def test_lookup_missing_returns_none() -> None:
    catalog = DataCatalog()
    assert catalog.get("ds-does-not-exist") is None


def test_list_by_owner() -> None:
    catalog = DataCatalog()
    catalog.register(_sample_source(name="a", owner="team-a"))
    catalog.register(_sample_source(name="b", owner="team-a"))
    catalog.register(_sample_source(name="c", owner="team-b"))
    assert {s.name for s in catalog.list_by_owner("team-a")} == {"a", "b"}
    assert {s.name for s in catalog.list_by_owner("team-b")} == {"c"}


def test_change_notice_event_on_register() -> None:
    catalog = DataCatalog()
    seen: list[dict[str, str]] = []
    catalog.subscribe(lambda ds: seen.append({"id": ds.dataset_id, "name": ds.name}))
    source = _sample_source()
    catalog.register(source)
    assert len(seen) == 1
    assert seen[0]["name"] == "customer_master"


def test_change_notice_on_unregister() -> None:
    catalog = DataCatalog()
    source = _sample_source()
    catalog.register(source)
    removed: list[str] = []
    catalog.subscribe_removal(lambda ds_id: removed.append(ds_id))
    catalog.unregister(source.dataset_id)
    assert removed == [source.dataset_id]
    assert catalog.get(source.dataset_id) is None
