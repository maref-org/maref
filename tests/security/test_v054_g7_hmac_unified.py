"""Tests for unified HMAC key distribution (INC-2026-08-13-001 / G7).

Verifies:
- state_machine falls back to .maraf_hmac_key when env is unset
- fail-closed raises + writes notification when no key at all
- sidecar create_app surfaces missing-key warning
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maref.governance.state_machine import GovernanceState, GovernanceStateMachine


class TestUnifiedHmacKey:
    def test_env_key_preferred(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "env-key-123")
        monkeypatch.setenv("MAREF_AUDIT_PATH", str(tmp_path))
        sm = GovernanceStateMachine()
        ok = sm.transition(GovernanceState.OBSERVE, "test-env-key")
        assert ok is True
        audit = tmp_path / "governance_audit.jsonl"
        assert audit.exists()
        line = audit.read_text().splitlines()[0]
        assert "env-key-123" not in line  # key 不落盘
        import json
        rec = json.loads(line)
        assert rec["event_type"] == "state_transition"
        assert "chain_hash" in rec

    def test_file_key_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 env 时从 .maraf_hmac_key 读取（G7-1 统一密钥源）。"""
        monkeypatch.delenv("MAREF_HMAC_SECRET_KEY", raising=False)
        monkeypatch.setenv("MAREF_AUDIT_PATH", str(tmp_path))
        key_file = tmp_path / ".maraf_hmac_key"
        key_file.write_text("file-key-456")
        with patch("maref.governance.state_machine.Path.cwd", return_value=tmp_path):
            sm = GovernanceStateMachine()
            ok = sm.transition(GovernanceState.OBSERVE, "test-file-key")
            assert ok is True
        audit = tmp_path / "governance_audit.jsonl"
        assert audit.exists()

    def test_no_key_fail_closed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 env 且无 key 文件时 fail-closed：transition 抛错且不写审计。"""
        monkeypatch.delenv("MAREF_HMAC_SECRET_KEY", raising=False)
        monkeypatch.setenv("MAREF_AUDIT_PATH", str(tmp_path))
        with patch("maref.governance.state_machine.Path.cwd", return_value=tmp_path), \
             patch("maref.governance.state_machine.Path.home", return_value=tmp_path):
            sm = GovernanceStateMachine()
            with pytest.raises(ValueError, match="MAREF_HMAC_SECRET_KEY"):
                sm.transition(GovernanceState.OBSERVE, "test-no-key")
        audit = tmp_path / "governance_audit.jsonl"
        assert not audit.exists()
        assert sm.current_state == GovernanceState.INIT  # 状态未变（fail-closed）


class TestSidecarStartupCheck:
    def test_create_app_warns_without_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """sidecar 无 key 启动时写 notification（G7-3）。"""
        from sidecar.server import create_app

        monkeypatch.delenv("MAREF_HMAC_SECRET_KEY", raising=False)
        # patch pathlib.Path（sidecar 内以 from pathlib import Path as _Path 使用）
        with patch("pathlib.Path.cwd", return_value=tmp_path), \
             patch("pathlib.Path.home", return_value=tmp_path):
            app = create_app(
                collector=None,  # type: ignore[arg-type]
                monitor=None,  # type: ignore[arg-type]
            )
            assert app is not None
        notifs = list((tmp_path / "notifications").glob("*audit-chain_critical.json"))
        assert len(notifs) >= 1
        import json
        rec = json.loads(notifs[0].read_text())
        assert rec["severity"] == "critical"
