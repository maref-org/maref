"""Tests for F1: Cross-Org Eight Trigrams State Sync."""

from __future__ import annotations

from maref.eivl.federated_merkle import FederatedMerkleAggregator
from maref.federation.trigram_sync import (
    AgentTrigramProof,
    TrigramStateSnapshot,
    TrigramStateSynchronizer,
)
from maref.recursive.eight_trigrams_governance import EightTrigramsGovernance


def _make_gov(agent_id: str, trust: float = 0.65) -> EightTrigramsGovernance:
    return EightTrigramsGovernance(agent_id=agent_id, initial_trust=trust)


# ------------------------------------------------------------------ #
# TrigramStateSnapshot
# ------------------------------------------------------------------ #

class TestTrigramStateSnapshot:
    def test_from_governance(self) -> None:
        gov = _make_gov("agent-01", trust=0.75)
        snap = TrigramStateSnapshot.from_governance(gov, "org-alpha")
        assert snap.agent_id == "agent-01"
        assert snap.org_id == "org-alpha"
        assert snap.trigram == "dui"
        assert snap.trust_score == 0.75

    def test_compute_hash_consistent(self) -> None:
        gov = _make_gov("agent-01")
        snap1 = TrigramStateSnapshot.from_governance(gov, "org-alpha")
        snap2 = TrigramStateSnapshot.from_governance(gov, "org-alpha")
        assert snap1.compute_hash() == snap2.compute_hash()

    def test_hash_changes_on_different_trust(self) -> None:
        gov1 = _make_gov("agent-01", trust=0.60)
        gov2 = _make_gov("agent-01", trust=0.80)
        s1 = TrigramStateSnapshot.from_governance(gov1, "org-alpha")
        s2 = TrigramStateSnapshot.from_governance(gov2, "org-alpha")
        assert s1.compute_hash() != s2.compute_hash()

    def test_hash_changes_on_different_org(self) -> None:
        gov = _make_gov("agent-01")
        s1 = TrigramStateSnapshot.from_governance(gov, "org-alpha")
        s2 = TrigramStateSnapshot.from_governance(gov, "org-beta")
        assert s1.compute_hash() != s2.compute_hash()

    def test_to_dict_roundtrip(self) -> None:
        gov = _make_gov("agent-01")
        snap = TrigramStateSnapshot.from_governance(gov, "org-alpha")
        d = snap.to_dict()
        assert d["agent_id"] == "agent-01"
        assert d["org_id"] == "org-alpha"
        assert d["trigram"] == "dui"


# ------------------------------------------------------------------ #
# TrigramStateSynchronizer — local state
# ------------------------------------------------------------------ #

class TestLocalState:
    def test_empty_synchronizer(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        assert sync.agent_count() == 0
        assert sync.get_local_root() is None

    def test_register_agent(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        gov = _make_gov("agent-01")
        snap = sync.register_agent(gov)
        assert snap.agent_id == "agent-01"
        assert sync.agent_count() == 1

    def test_register_multiple_agents_builds_tree(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        sync.register_agent(_make_gov("agent-02"))
        sync.register_agent(_make_gov("agent-03"))
        assert sync.agent_count() == 3
        root = sync.get_local_root()
        assert root is not None
        assert len(root) == 64  # SHA-256 hex

    def test_unregister_agent(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        sync.register_agent(_make_gov("agent-02"))
        assert sync.unregister_agent("agent-01") is True
        assert sync.agent_count() == 1
        assert sync.unregister_agent("nonexistent") is False

    def test_get_snapshot(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        snap = sync.register_agent(_make_gov("agent-01"))
        retrieved = sync.get_snapshot("agent-01")
        assert retrieved is not None
        assert retrieved.agent_id == snap.agent_id
        assert sync.get_snapshot("nonexistent") is None

    def test_refresh_snapshot(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        gov = _make_gov("agent-01", trust=0.65)
        sync.register_agent(gov)
        gov._state.trust_score = 0.90
        gov.auto_transition(0.90)
        updated = sync.refresh_snapshot(gov)
        assert updated is not None
        assert updated.trust_score == 0.90
        assert updated.trigram != "dui"

    def test_refresh_snapshot_unregistered(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        gov = _make_gov("agent-unknown")
        assert sync.refresh_snapshot(gov) is None

    def test_list_agents(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        sync.register_agent(_make_gov("agent-02"))
        agents = sync.list_agents()
        assert len(agents) == 2


# ------------------------------------------------------------------ #
# Agent Merkle proofs
# ------------------------------------------------------------------ #

class TestAgentProof:
    def test_generate_proof_single_agent(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        proof = sync.generate_agent_proof("agent-01")
        assert proof is not None
        assert proof.org_id == "org-alpha"
        assert proof.snapshot.agent_id == "agent-01"
        assert proof.verify_local() is True

    def test_generate_proof_multiple_agents(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        sync.register_agent(_make_gov("agent-02"))
        sync.register_agent(_make_gov("agent-03"))
        proof = sync.generate_agent_proof("agent-02")
        assert proof is not None
        assert proof.verify_local() is True

    def test_proof_fails_for_unknown_agent(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        assert sync.generate_agent_proof("nonexistent") is None

    def test_proof_fails_for_empty_sync(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        assert sync.generate_agent_proof("agent-01") is None

    def test_proof_detects_tampered_hash(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        sync.register_agent(_make_gov("agent-02"))
        proof = sync.generate_agent_proof("agent-01")
        assert proof is not None
        assert proof.verify_local() is True
        tampered = AgentTrigramProof(
            snapshot=proof.snapshot,
            local_proof_path=proof.local_proof_path,
            org_trigram_root="0" * 64,
            org_id=proof.org_id,
        )
        assert tampered.verify_local() is False

    def test_proof_to_dict(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        proof = sync.generate_agent_proof("agent-01")
        assert proof is not None
        d = proof.to_dict()
        assert d["org_id"] == "org-alpha"
        assert d["snapshot"]["agent_id"] == "agent-01"


# ------------------------------------------------------------------ #
# Cross-org publish / import / verify
# ------------------------------------------------------------------ #

class TestCrossOrgSync:
    def test_publish_local_state(self) -> None:
        agg = FederatedMerkleAggregator()
        sync = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        sync.register_agent(_make_gov("agent-01"))
        fed_root = sync.publish_local_state()
        assert fed_root is not None
        assert agg.summary()["org_count"] == 1

    def test_publish_empty_returns_none(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        assert sync.publish_local_state() is None

    def test_publish_without_aggregator_returns_none(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        assert sync.publish_local_state() is None

    def test_import_remote_snapshot_valid(self) -> None:
        # Org-alpha publishes
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01"))
        alpha_proof = alpha.generate_agent_proof("agent-01")
        assert alpha_proof is not None

        # Org-beta imports
        beta = TrigramStateSynchronizer(org_id="org-beta")
        result = beta.import_remote_snapshot(alpha_proof.snapshot, alpha_proof)
        assert result is True

    def test_import_remote_snapshot_rejects_tampered(self) -> None:
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01"))
        proof = alpha.generate_agent_proof("agent-01")
        assert proof is not None

        tampered_snap = TrigramStateSnapshot(
            agent_id="agent-01",
            org_id="org-alpha",
            trigram="qian",
            trust_score=0.99,
        )
        beta = TrigramStateSynchronizer(org_id="org-beta")
        result = beta.import_remote_snapshot(tampered_snap, proof)
        assert result is False

    def test_import_rejects_wrong_org(self) -> None:
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01"))
        proof = alpha.generate_agent_proof("agent-01")
        assert proof is not None

        wrong_org_snap = TrigramStateSnapshot(
            agent_id="agent-01",
            org_id="org-gamma",
            trigram="dui",
            trust_score=0.65,
        )
        beta = TrigramStateSynchronizer(org_id="org-beta")
        result = beta.import_remote_snapshot(wrong_org_snap, proof)
        assert result is False

    def test_verify_remote_inclusion(self) -> None:
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01"))
        proof = alpha.generate_agent_proof("agent-01")
        assert proof is not None
        alpha.publish_local_state()

        beta = TrigramStateSynchronizer(org_id="org-beta", merkle_aggregator=agg)
        beta.import_remote_snapshot(proof.snapshot, proof)
        assert beta.verify_remote_inclusion("org-alpha", "agent-01") is True

    def test_verify_remote_inclusion_unknown_org(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-beta")
        assert sync.verify_remote_inclusion("org-unknown", "agent-01") is False


# ------------------------------------------------------------------ #
# Drift detection
# ------------------------------------------------------------------ #

class TestDriftDetection:
    def test_no_drift_when_identical(self) -> None:
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01", trust=0.75))
        proof = alpha.generate_agent_proof("agent-01")
        assert proof is not None

        beta = TrigramStateSynchronizer(org_id="org-beta")
        beta.register_agent(_make_gov("agent-01", trust=0.75))
        beta.import_remote_snapshot(proof.snapshot, proof)
        drift = beta.detect_drift("org-alpha")
        assert len(drift) == 1
        assert drift[0]["drift_detected"] is False

    def test_drift_detected_on_different_trigram(self) -> None:
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01", trust=0.75))
        proof = alpha.generate_agent_proof("agent-01")
        assert proof is not None

        beta_gov = _make_gov("agent-01", trust=0.95)
        beta_gov.auto_transition(0.95)
        beta = TrigramStateSynchronizer(org_id="org-beta")
        beta.register_agent(beta_gov)
        beta.import_remote_snapshot(proof.snapshot, proof)
        drift = beta.detect_drift("org-alpha")
        assert len(drift) == 1
        assert drift[0]["drift_detected"] is True
        assert drift[0]["local_trigram"] != drift[0]["remote_trigram"]

    def test_drift_detected_on_trust_diff(self) -> None:
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01", trust=0.75))
        proof = alpha.generate_agent_proof("agent-01")
        assert proof is not None

        beta = TrigramStateSynchronizer(org_id="org-beta")
        beta.register_agent(_make_gov("agent-01", trust=0.90))
        beta.import_remote_snapshot(proof.snapshot, proof)
        drift = beta.detect_drift("org-alpha")
        assert drift[0]["drift_detected"] is True

    def test_drift_empty_when_no_remote(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        sync.register_agent(_make_gov("agent-01"))
        assert sync.detect_drift() == []

    def test_drift_filtered_by_org(self) -> None:
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01"))
        proof = alpha.generate_agent_proof("agent-01")
        assert proof is not None

        beta = TrigramStateSynchronizer(org_id="org-beta")
        beta.import_remote_snapshot(proof.snapshot, proof)
        drift = beta.detect_drift(org_id="org-gamma")
        assert drift == []


# ------------------------------------------------------------------ #
# Sync summary
# ------------------------------------------------------------------ #

class TestSyncSummary:
    def test_summary_empty(self) -> None:
        sync = TrigramStateSynchronizer(org_id="org-alpha")
        s = sync.sync_summary()
        assert s["org_id"] == "org-alpha"
        assert s["local_agent_count"] == 0
        assert s["remote_org_count"] == 0

    def test_summary_with_agents(self) -> None:
        agg = FederatedMerkleAggregator()
        sync = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        sync.register_agent(_make_gov("agent-01"))
        sync.register_agent(_make_gov("agent-02"))
        sync.publish_local_state()
        s = sync.sync_summary()
        assert s["local_agent_count"] == 2
        assert s["local_trigram_root"] is not None
        assert s["federated_root"] is not None

    def test_summary_with_remote_orgs(self) -> None:
        agg = FederatedMerkleAggregator()
        alpha = TrigramStateSynchronizer(org_id="org-alpha", merkle_aggregator=agg)
        alpha.register_agent(_make_gov("agent-01"))
        proof = alpha.generate_agent_proof("agent-01")
        assert proof is not None

        beta = TrigramStateSynchronizer(org_id="org-beta")
        beta.import_remote_snapshot(proof.snapshot, proof)
        s = beta.sync_summary()
        assert s["remote_org_count"] == 1
        assert s["remote_agent_count"] == 1
