"""Unit tests for FederatedCatalog."""

from __future__ import annotations

import time

import pytest

from maref.federation.catalog import (
    CatalogEntry,
    CatalogSubscription,
    FederatedCatalog,
)
from maref.federation.gateway import FederatedAgent


class TestCatalogPublish:
    def test_publish_creates_entry(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        entry = catalog.publish(agent)
        assert entry.agent.aic.aic_string == agent.aic.aic_string
        assert entry.version == 1
        assert catalog.entry_count == 1

    def test_publish_updates_existing_increments_version(
        self, make_federated_agent
    ) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        catalog.publish(agent)
        # Re-publish the same agent (same AIC) — should update, not duplicate.
        time.sleep(0.01)
        entry = catalog.publish(agent, tags=["updated"])
        assert entry.version == 2
        assert entry.tags == ["updated"]
        assert catalog.entry_count == 1
        assert entry.updated_at >= entry.published_at

    def test_publish_with_tags(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        entry = catalog.publish(agent, tags=["beta", "internal"])
        assert entry.tags == ["beta", "internal"]


class TestCatalogUnpublish:
    def test_unpublish_existing(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        catalog.publish(agent)
        assert catalog.unpublish(agent.aic.aic_string) is True
        assert catalog.entry_count == 0
        assert catalog.get_by_aic(agent.aic.aic_string) is None

    def test_unpublish_nonexistent_returns_false(self) -> None:
        catalog = FederatedCatalog()
        assert catalog.unpublish("nonexistent-aic") is False

    def test_unpublish_cleans_did_index(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        catalog.publish(agent)
        did_str = agent.did.did_string
        assert catalog.get_by_did(did_str) is not None
        catalog.unpublish(agent.aic.aic_string)
        assert catalog.get_by_did(did_str) is None


class TestCatalogLookup:
    def test_get_by_aic(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        catalog.publish(agent)
        entry = catalog.get_by_aic(agent.aic.aic_string)
        assert entry is not None
        assert entry.agent.did.did_string == agent.did.did_string

    def test_get_by_aic_missing(self) -> None:
        catalog = FederatedCatalog()
        assert catalog.get_by_aic("missing") is None

    def test_get_by_did(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        catalog.publish(agent)
        entry = catalog.get_by_did(agent.did.did_string)
        assert entry is not None
        assert entry.agent.aic.aic_string == agent.aic.aic_string

    def test_get_by_did_missing(self) -> None:
        catalog = FederatedCatalog()
        assert catalog.get_by_did("did:maref:federated:missing") is None


class TestCatalogQuery:
    def test_query_by_capability(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        a1 = make_federated_agent(skills=["research"])
        a2 = make_federated_agent(skills=["analysis"])
        catalog.publish(a1)
        catalog.publish(a2)
        results = catalog.query(capability="research")
        assert len(results) == 1
        assert results[0].agent.aic.aic_string == a1.aic.aic_string

    def test_query_by_protocol(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        aip_agent = make_federated_agent(skills=["research"], protocol="aip")
        a2a_agent = make_federated_agent(skills=["research"], protocol="a2a")
        catalog.publish(aip_agent)
        catalog.publish(a2a_agent)
        results = catalog.query(protocol="a2a")
        assert len(results) == 1
        assert results[0].agent.protocol == "a2a"

    def test_query_by_organization(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        org_a = make_federated_agent(skills=["research"], organization="OrgA")
        org_b = make_federated_agent(skills=["research"], organization="OrgB")
        catalog.publish(org_a)
        catalog.publish(org_b)
        results = catalog.query(organization="OrgA")
        assert len(results) == 1
        assert results[0].agent.aic.aic_string == org_a.aic.aic_string

    def test_query_by_tag(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        a1 = make_federated_agent(skills=["research"])
        a2 = make_federated_agent(skills=["research"])
        catalog.publish(a1, tags=["beta"])
        catalog.publish(a2, tags=["stable"])
        results = catalog.query(tag="beta")
        assert len(results) == 1
        assert results[0].agent.aic.aic_string == a1.aic.aic_string

    def test_query_multiple_filters_and_combined(
        self, make_federated_agent
    ) -> None:
        catalog = FederatedCatalog()
        # Matches both filters.
        match = make_federated_agent(skills=["research"], organization="OrgA")
        # Matches capability only.
        cap_only = make_federated_agent(skills=["research"], organization="OrgB")
        # Matches org only.
        org_only = make_federated_agent(skills=["analysis"], organization="OrgA")
        catalog.publish(match)
        catalog.publish(cap_only)
        catalog.publish(org_only)
        results = catalog.query(capability="research", organization="OrgA")
        assert len(results) == 1
        assert results[0].agent.aic.aic_string == match.aic.aic_string

    def test_query_no_filters_returns_all(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        catalog.publish(make_federated_agent(skills=["research"]))
        catalog.publish(make_federated_agent(skills=["analysis"]))
        results = catalog.query()
        assert len(results) == 2

    def test_query_limit(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        for _ in range(5):
            catalog.publish(make_federated_agent(skills=["research"]))
        results = catalog.query(capability="research", limit=2)
        assert len(results) == 2

    def test_query_sorted_by_updated_at_desc(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        a1 = make_federated_agent(skills=["research"])
        catalog.publish(a1)
        time.sleep(0.02)
        a2 = make_federated_agent(skills=["research"])
        catalog.publish(a2)
        results = catalog.query(capability="research")
        # Most recently updated first.
        assert results[0].agent.aic.aic_string == a2.aic.aic_string
        assert results[1].agent.aic.aic_string == a1.aic.aic_string


class TestCatalogListings:
    def test_list_capabilities(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        catalog.publish(make_federated_agent(skills=["research", "analysis"]))
        catalog.publish(make_federated_agent(skills=["translation"]))
        caps = catalog.list_capabilities()
        assert caps == ["analysis", "research", "translation"]

    def test_list_organizations(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        catalog.publish(make_federated_agent(skills=["research"], organization="OrgB"))
        catalog.publish(make_federated_agent(skills=["research"], organization="OrgA"))
        orgs = catalog.list_organizations()
        assert orgs == ["OrgA", "OrgB"]

    def test_list_protocols(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        catalog.publish(make_federated_agent(skills=["research"], protocol="a2a"))
        catalog.publish(make_federated_agent(skills=["research"], protocol="aip"))
        protos = catalog.list_protocols()
        assert protos == ["a2a", "aip"]

    def test_indices_cleaned_on_unpublish(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        catalog.publish(agent)
        assert "research" in catalog.list_capabilities()
        catalog.unpublish(agent.aic.aic_string)
        assert "research" not in catalog.list_capabilities()


class TestCatalogSubscription:
    def test_subscribe_receives_updates(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        received: list[CatalogEntry] = []
        sub_id = catalog.subscribe(lambda e: received.append(e))
        agent = make_federated_agent(skills=["research"])
        catalog.publish(agent)
        assert len(received) == 1
        assert received[0].agent.aic.aic_string == agent.aic.aic_string
        assert catalog.subscription_count == 1
        assert sub_id.startswith("sub-")

    def test_subscribe_with_capability_filter(
        self, make_federated_agent
    ) -> None:
        catalog = FederatedCatalog()
        received: list[CatalogEntry] = []
        catalog.subscribe(lambda e: received.append(e), capability_filter="research")
        # Publishing an agent WITHOUT "research" should not trigger callback.
        other = make_federated_agent(skills=["analysis"])
        catalog.publish(other)
        assert received == []
        # Publishing an agent WITH "research" triggers it.
        match = make_federated_agent(skills=["research"])
        catalog.publish(match)
        assert len(received) == 1

    def test_subscribe_receives_update_on_republish(
        self, make_federated_agent
    ) -> None:
        catalog = FederatedCatalog()
        received: list[CatalogEntry] = []
        catalog.subscribe(lambda e: received.append(e))
        agent = make_federated_agent(skills=["research"])
        catalog.publish(agent)
        catalog.publish(agent)  # update
        assert len(received) == 2

    def test_unsubscribe_stops_notifications(
        self, make_federated_agent
    ) -> None:
        catalog = FederatedCatalog()
        received: list[CatalogEntry] = []
        sub_id = catalog.subscribe(lambda e: received.append(e))
        assert catalog.unsubscribe(sub_id) is True
        assert catalog.subscription_count == 0
        catalog.publish(make_federated_agent(skills=["research"]))
        assert received == []
        assert catalog.unsubscribe(sub_id) is False

    def test_subscriber_error_is_swallowed(self, make_federated_agent) -> None:
        """A failing callback must not break catalog publish."""
        catalog = FederatedCatalog()

        def bad_callback(_entry: CatalogEntry) -> None:
            raise RuntimeError("subscriber exploded")

        catalog.subscribe(bad_callback)
        # This must not raise.
        agent = make_federated_agent(skills=["research"])
        entry = catalog.publish(agent)
        assert entry.agent.aic.aic_string == agent.aic.aic_string
        assert catalog.entry_count == 1


class TestCatalogSummary:
    def test_catalog_summary(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        catalog.publish(make_federated_agent(skills=["research"], organization="OrgA"))
        catalog.publish(make_federated_agent(skills=["analysis"], organization="OrgB"))
        catalog.subscribe(lambda e: None, capability_filter="research")
        summary = catalog.catalog_summary()
        assert summary["entry_count"] == 2
        assert summary["capability_count"] == 2
        assert summary["organization_count"] == 2
        assert summary["protocol_count"] == 1  # both default "aip"
        assert summary["active_subscriptions"] == 1

    def test_subscription_count_excludes_inactive(
        self, make_federated_agent
    ) -> None:
        catalog = FederatedCatalog()
        sub_id = catalog.subscribe(lambda e: None)
        catalog.subscribe(lambda e: None)
        assert catalog.subscription_count == 2
        catalog.unsubscribe(sub_id)
        assert catalog.subscription_count == 1


class TestCatalogEntryToDict:
    def test_to_dict(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research", "analysis"])
        entry = catalog.publish(agent, tags=["t1"])
        d = entry.to_dict()
        assert d["aic"] == agent.aic.aic_string
        assert d["did"] == agent.did.did_string
        assert d["name"] == agent.acs.name
        assert d["organization"] == "TestOrg"
        assert d["protocol"] == "aip"
        assert set(d["capabilities"]) == {"research", "analysis"}
        assert d["tags"] == ["t1"]
        assert d["version"] == 1


class TestCatalogSubscriptionMatches:
    def test_inactive_subscription_does_not_match(
        self, make_federated_agent
    ) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        entry = catalog.publish(agent)
        sub = CatalogSubscription(
            subscription_id="x",
            callback=lambda e: None,
            active=False,
        )
        assert sub.matches(entry) is False

    def test_no_filter_matches_all(self, make_federated_agent) -> None:
        catalog = FederatedCatalog()
        agent = make_federated_agent(skills=["research"])
        entry = catalog.publish(agent)
        sub = CatalogSubscription(subscription_id="x", callback=lambda e: None)
        assert sub.matches(entry) is True
