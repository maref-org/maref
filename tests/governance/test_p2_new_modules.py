"""Tests for P2 new modules: health_snapshot, security_audit_chain, self_saeb, PulseWriter."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from maref.governance.security_audit_chain import SecurityAuditChain, SecurityAuditEntry
from maref.immunity.negative_gene_bank import NegativeGeneBank
from maref.immunity.self_saeb import SelfSAEBRunner
from maref.observability.health_snapshot import HealthSnapshotWriter
from maref.recursive.agent_health import PulseWriter


class TestHealthSnapshotWriter:
    """Tests for HealthSnapshotWriter (M0.1)."""

    def test_write_and_read_snapshot(self, tmp_path: Path) -> None:
        w = HealthSnapshotWriter(snapshot_path=tmp_path / "snap.json")
        w.write_snapshot(status="healthy", active_agents=3)
        snap = w.read_snapshot()
        assert snap is not None
        assert snap["status"] == "healthy"
        assert snap["active_agents"] == 3
        assert "timestamp" in snap
        assert "pid" in snap

    def test_is_fresh_within_threshold(self, tmp_path: Path) -> None:
        w = HealthSnapshotWriter(snapshot_path=tmp_path / "snap.json")
        w.write_snapshot()
        assert w.is_fresh(max_age_seconds=120) is True

    def test_is_fresh_expired(self, tmp_path: Path) -> None:
        w = HealthSnapshotWriter(snapshot_path=tmp_path / "snap.json")
        # Don't write anything
        assert w.is_fresh(max_age_seconds=120) is False

    def test_error_tracking(self, tmp_path: Path) -> None:
        w = HealthSnapshotWriter(snapshot_path=tmp_path / "snap.json")
        w.record_error()
        w.record_error()
        w.write_snapshot()
        snap = w.read_snapshot()
        assert snap["consecutive_errors"] == 2

    def test_reset_errors(self, tmp_path: Path) -> None:
        w = HealthSnapshotWriter(snapshot_path=tmp_path / "snap.json")
        w.record_error()
        w.reset_errors()
        w.write_snapshot()
        snap = w.read_snapshot()
        assert snap["consecutive_errors"] == 0

    def test_extra_fields(self, tmp_path: Path) -> None:
        w = HealthSnapshotWriter(snapshot_path=tmp_path / "snap.json")
        w.write_snapshot(extra={"custom": "value"})
        snap = w.read_snapshot()
        assert snap["extra"]["custom"] == "value"


class TestPulseWriter:
    """Tests for PulseWriter (M0.3)."""

    def test_write_pulse(self, tmp_path: Path) -> None:
        p = PulseWriter("agent-1", pulses_dir=tmp_path, interval_seconds=30.0)
        pulse = p.write_pulse(status="alive")
        assert pulse["agent"] == "agent-1"
        assert pulse["status"] == "alive"
        assert pulse["interval"] == 30.0
        assert "timestamp" in pulse
        assert "pid" in pulse

    def test_is_alive_fresh(self, tmp_path: Path) -> None:
        p = PulseWriter("agent-1", pulses_dir=tmp_path, interval_seconds=30.0)
        p.write_pulse()
        assert p.is_alive() is True

    def test_is_alive_stale(self, tmp_path: Path) -> None:
        p = PulseWriter("agent-1", pulses_dir=tmp_path, interval_seconds=0.001)
        p.write_pulse()
        time.sleep(0.01)  # Wait past interval * 3
        assert p.is_alive() is False

    def test_is_alive_no_file(self, tmp_path: Path) -> None:
        p = PulseWriter("agent-1", pulses_dir=tmp_path, interval_seconds=30.0)
        assert p.is_alive() is False

    def test_check_pulse_staleness_empty(self, tmp_path: Path) -> None:
        result = PulseWriter.check_pulse_staleness(tmp_path)
        assert result["total"] == 0
        assert result["status"] == "no_pulses"

    def test_check_pulse_staleness_all_fresh(self, tmp_path: Path) -> None:
        for i in range(3):
            p = PulseWriter(f"agent-{i}", pulses_dir=tmp_path, interval_seconds=30.0)
            p.write_pulse()
        result = PulseWriter.check_pulse_staleness(tmp_path)
        assert result["total"] == 3
        assert result["stale"] == 0
        assert result["status"] == "healthy"

    def test_check_pulse_staleness_with_stale(self, tmp_path: Path) -> None:
        # Create fresh pulse
        p1 = PulseWriter("fresh", pulses_dir=tmp_path, interval_seconds=30.0)
        p1.write_pulse()
        # Create stale pulse manually
        stale_data = {"agent": "stale", "timestamp": time.time() - 1000, "interval": 30.0}
        with open(tmp_path / "stale.json", "w") as f:
            json.dump(stale_data, f)
        result = PulseWriter.check_pulse_staleness(tmp_path)
        assert result["total"] == 2
        assert result["stale"] == 1
        assert "stale" in result["stale_agents"]

    def test_cycle_increments(self, tmp_path: Path) -> None:
        p = PulseWriter("agent-1", pulses_dir=tmp_path)
        p1 = p.write_pulse()
        p2 = p.write_pulse()
        assert p2["cycle"] == p1["cycle"] + 1


class TestSecurityAuditChain:
    """Tests for SecurityAuditChain."""

    def test_append_and_read(self, tmp_path: Path) -> None:
        chain = SecurityAuditChain(
            chain_path=tmp_path / "chain.jsonl",
            hmac_key="test_key",
        )
        entry = chain.append(
            event_type="auth",
            actor="user1",
            action="login",
            severity="INFO",
        )
        assert entry.event_type == "auth"
        assert entry.chain_hash != ""
        assert entry.hmac_signature != ""

        entries = chain.read_all()
        assert len(entries) == 1
        assert entries[0]["actor"] == "user1"

    def test_chain_linkage(self, tmp_path: Path) -> None:
        chain = SecurityAuditChain(
            chain_path=tmp_path / "chain.jsonl",
            hmac_key="test_key",
        )
        e1 = chain.append("auth", "user1", "login")
        e2 = chain.append("access", "user1", "read_file")
        assert e2.previous_hash == e1.chain_hash

    def test_verify_integrity_valid(self, tmp_path: Path) -> None:
        chain = SecurityAuditChain(
            chain_path=tmp_path / "chain.jsonl",
            hmac_key="test_key",
        )
        chain.append("auth", "user1", "login")
        chain.append("access", "user1", "read")
        result = chain.verify_integrity()
        assert result["status"] == "verified"
        assert result["tampered"] == 0

    def test_verify_integrity_tampered(self, tmp_path: Path) -> None:
        path = tmp_path / "chain.jsonl"
        chain = SecurityAuditChain(chain_path=path, hmac_key="test_key")
        chain.append("auth", "user1", "login")
        # Tamper with the file
        with open(path) as f:
            lines = f.readlines()
        data = json.loads(lines[0])
        data["action"] = "malicious"
        lines[0] = json.dumps(data) + "\n"
        with open(path, "w") as f:
            f.writelines(lines)
        result = chain.verify_integrity()
        assert result["status"] == "tampered"
        assert result["tampered"] > 0

    def test_no_hmac_key_warning(self, tmp_path: Path, caplog) -> None:
        with tempfile.TemporaryDirectory() as td:
            old_cwd = os.getcwd()
            os.chdir(td)
            try:
                chain = SecurityAuditChain(chain_path=Path(td) / "chain.jsonl")
                entry = chain.append("test", "actor", "action")
                assert entry.hmac_signature == ""
                assert "No HMAC key" in caplog.text
            finally:
                os.chdir(old_cwd)

    def test_empty_chain_verify(self, tmp_path: Path) -> None:
        chain = SecurityAuditChain(
            chain_path=tmp_path / "chain.jsonl",
            hmac_key="test_key",
        )
        result = chain.verify_integrity()
        assert result["status"] == "no_file"
        assert result["total"] == 0


class TestSelfSAEB:
    """Tests for SelfSAEBRunner."""

    def test_run_self_saeb(self) -> None:
        bank = NegativeGeneBank()  # In-memory, empty
        runner = SelfSAEBRunner(bank, detection_threshold=0.0)
        result = runner.run_self_saeb()
        assert result.total_samples > 0
        assert result.timestamp > 0
        assert isinstance(result.details, list)

    def test_degradation_check_no_history(self) -> None:
        bank = NegativeGeneBank()
        runner = SelfSAEBRunner(bank)
        result = runner.check_degradation()
        assert result["status"] == "no_history"

    def test_degradation_check_baseline(self) -> None:
        bank = NegativeGeneBank()
        runner = SelfSAEBRunner(bank)
        runner.run_self_saeb()
        result = runner.check_degradation()
        assert result["status"] == "baseline_established"

    def test_degradation_check_healthy(self) -> None:
        bank = NegativeGeneBank()
        runner = SelfSAEBRunner(bank, detection_threshold=0.0)
        runner.run_self_saeb()
        runner.run_self_saeb()
        result = runner.check_degradation()
        assert "current_rate" in result
        assert "previous_rate" in result

    def test_to_dict(self) -> None:
        bank = NegativeGeneBank()
        runner = SelfSAEBRunner(bank, detection_threshold=0.0)
        result = runner.run_self_saeb()
        d = result.to_dict()
        assert "detection_rate" in d
        assert "gene_count" in d
        assert "degraded" in d
