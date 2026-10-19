"""Tests for content provenance, licensing, and lineage (P1-B)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maref.governance.content_provenance import (
    AssetProvenance,
    ProvenanceLedger,
    SourceRef,
)


def test_register_hashes_content_and_checks_license():
    ledger = ProvenanceLedger()
    asset = ledger.register("article-1", content="hello", license="MIT")
    assert asset.content_hash
    assert asset.record_hash
    assert ledger.check_publishable("article-1").allowed is True


def test_unregistered_asset_cannot_publish():
    ledger = ProvenanceLedger()
    decision = ledger.check_publishable("missing")
    assert decision.allowed is False
    assert "not registered" in decision.reason


def test_unknown_license_fails_closed():
    ledger = ProvenanceLedger()
    ledger.register("article-1", content="hello", license="unknown")
    decision = ledger.check_publishable("article-1")
    assert decision.allowed is False
    assert "not allowed" in decision.reason


def test_source_license_is_checked():
    ledger = ProvenanceLedger()
    ledger.register(
        "article-1",
        content="hello",
        license="MIT",
        sources=[SourceRef(uri="https://example.com", license="GPL-3.0")],
    )
    decision = ledger.check_publishable("article-1")
    assert decision.allowed is False
    assert "GPL-3.0" in decision.reason


def test_ai_asset_requires_model_and_prompt():
    ledger = ProvenanceLedger()
    ledger.register("gen-1", content="ai", license="MIT", ai_generated=True)
    decision = ledger.check_publishable("gen-1")
    assert decision.allowed is False
    assert "model and prompt_hash" in decision.reason


def test_lineage_collects_ancestors():
    ledger = ProvenanceLedger()
    ledger.register("source", content="raw", license="MIT")
    ledger.register("draft", content="draft", license="MIT", parent_ids=["source"])
    ledger.register("final", content="final", license="MIT", parent_ids=["draft"])
    lineage = ledger.lineage("final")
    assert [asset.asset_id for asset in lineage] == ["source", "draft"]


def test_strict_lineage_rejects_unknown_parent():
    ledger = ProvenanceLedger(strict_lineage=True)
    with pytest.raises(ValueError, match="unknown parent"):
        ledger.register("final", content="final", license="MIT", parent_ids=["missing"])


def test_parent_license_blocks_publish():
    ledger = ProvenanceLedger()
    ledger.register("source", content="raw", license="unknown")
    ledger.register("final", content="final", license="MIT", parent_ids=["source"])
    decision = ledger.check_publishable("final")
    assert decision.allowed is False
    assert "parent asset" in decision.reason


def test_integrity_detects_tampering():
    ledger = ProvenanceLedger()
    ledger.register("one", content="one", license="MIT")
    ledger.register("two", content="two", license="MIT")
    assert ledger.verify_integrity() is True
    ledger._assets["one"].content_hash = "tampered"  # noqa: SLF001
    assert ledger.verify_integrity() is False


def test_persists_and_reloads_ledger(tmp_path: Path):
    path = tmp_path / "provenance.jsonl"
    ledger = ProvenanceLedger(path)
    ledger.register("one", content="one", license="MIT", sources=[SourceRef(uri="local")])
    restored = ProvenanceLedger(path)
    asset = restored.get("one")
    assert isinstance(asset, AssetProvenance)
    assert asset is not None
    assert asset.sources[0].uri == "local"
    assert restored.verify_integrity() is True


def test_manifest_contains_assets_and_integrity():
    ledger = ProvenanceLedger()
    ledger.register("one", content="one", license="MIT")
    manifest = ledger.export_manifest()
    assert manifest["asset_count"] == 1
    assert manifest["integrity"] is True


def test_empty_allowlist_denies_every_license():
    ledger = ProvenanceLedger()
    ledger.register("one", content="one", license="MIT")
    decision = ledger.check_publishable("one", allowed_licenses=[])
    assert decision.allowed is False
    assert "not allowed" in decision.reason
