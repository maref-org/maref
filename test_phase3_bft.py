#!/usr/bin/env python3
"""Phase 3.1 BFT HMAC-SHA256 signature tests."""

from __future__ import annotations

from maref.recursive.distributed_bft import DistributedBFT, Vote


def test_vote_sign_and_verify():
    key = b"test-secret"
    vote = Vote(node_id="n1", value="approve", round_number=1)
    vote.sign(key)
    assert vote.hmac_signature != ""
    assert vote.verify(key)
    print("  vote_sign_and_verify OK")


def test_tampered_vote_fails_verification():
    key = b"test-secret"
    vote = Vote(node_id="n1", value="approve", round_number=1)
    vote.sign(key)
    vote.value = "reject"  # tamper
    assert not vote.verify(key)
    print("  tampered_vote_fails_verification OK")


def test_bft_consensus_with_signatures():
    key = b"maref-bft-key"
    bft = DistributedBFT(total_nodes=5, secret_key=key)
    bft.register_nodes(5)

    r = bft.run_consensus_cycle("deploy_v2")
    assert r.result.value == "reached"

    # All honest votes should verify
    summary = bft.verify_all_signatures(len(bft._rounds) - 1)
    assert summary["verified"] >= bft.quorum
    assert summary["failed"] == 0
    print("  bft_consensus_with_signatures OK")


def test_bft_rejects_tampered_vote():
    key = b"maref-bft-key"
    bft = DistributedBFT(total_nodes=5, secret_key=key)
    bft.register_nodes(5)

    r = bft.propose_consensus("deploy_v2")
    ri = len(bft._rounds) - 1

    # Cast honest vote
    v = bft.cast_vote(ri, "node_0", "deploy_v2")
    assert v is not None
    assert v.verify(key)

    # Tamper the vote after casting
    v.value = "malicious_value"
    v.hmac_signature = ""

    # Cast remaining honest votes
    for i in range(1, 5):
        bft.cast_vote(ri, f"node_{i}", "deploy_v2")

    bft.reach_consensus(ri)
    # The tampered vote is marked byzantine during reach_consensus,
    # so verify_all_signatures skips it.  Consensus still succeeds with
    # 4 honest votes (quorum=4 for 5 nodes).  Verify byzantine count.
    summary = bft.verify_all_signatures(ri)
    assert summary["byzantine"] >= 1
    print("  bft_rejects_tampered_vote OK")


def test_audit_log_populated():
    bft = DistributedBFT(total_nodes=5)
    bft.register_nodes(5)
    bft.run_consensus_cycle("value_x")
    assert len(bft._audit_log) == 1
    entry = bft._audit_log[0]
    assert entry["signature_verified"] is True
    assert "decided_value" in entry
    print("  audit_log_populated OK")


if __name__ == "__main__":
    test_vote_sign_and_verify()
    test_tampered_vote_fails_verification()
    test_bft_consensus_with_signatures()
    test_bft_rejects_tampered_vote()
    test_audit_log_populated()
    print("All Phase 3 BFT tests passed")
