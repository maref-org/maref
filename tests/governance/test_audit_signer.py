"""AuditSigner 单元测试 — 带外签署最小增量(P0-3).

覆盖：本地 HMAC 字节一致性、缺钥 fail-closed、远程签署成功/回退/降级标记、
环境变量驱动的后端选择，以及状态机接线。
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

import pytest

from maref.governance import state_machine as sm_mod
from maref.governance.audit_signer import (
    AuditKeyMissingError,
    LocalHmacSigner,
    RemoteSignerClient,
    resolve_audit_signer,
    resolve_local_hmac_key,
)
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


class TestLocalHmacSigner:
    def test_byte_identical_to_hmac(self) -> None:
        signer = LocalHmacSigner(key=b"secret-key")
        payload = b'{"event_type": "state_transition"}'
        expected = hmac.new(b"secret-key", payload, hashlib.sha256).hexdigest()
        assert signer.sign(payload) == expected

    def test_missing_key_raises(self) -> None:
        signer = LocalHmacSigner(key=b"")
        assert signer.has_key is False
        with pytest.raises(AuditKeyMissingError):
            signer.sign(b"x")

    def test_backend_name_and_degraded(self) -> None:
        signer = LocalHmacSigner(key=b"k")
        assert signer.backend_name == "local-hmac"
        assert signer.degraded is False


class TestResolveLocalKey:
    def test_env_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "env-key")
        assert resolve_local_hmac_key() == b"env-key"

    def test_file_fallback(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("MAREF_HMAC_SECRET_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".maraf_hmac_key").write_text("file-key", encoding="utf-8")
        assert resolve_local_hmac_key() == b"file-key"


class TestRemoteSignerClient:
    def test_remote_success(self) -> None:
        client = RemoteSignerClient(
            "http://sidecar/sign",
            transport=lambda url, payload, timeout: "remote-sig",
            fallback=LocalHmacSigner(key=b"local"),
        )
        assert client.sign(b"data") == "remote-sig"
        assert client.degraded is False

    def test_fallback_on_failure_marks_degraded(self) -> None:
        def boom(url: str, payload: bytes, timeout: float) -> str:
            raise ConnectionError("sidecar down")

        client = RemoteSignerClient(
            "http://sidecar/sign",
            transport=boom,
            fallback=LocalHmacSigner(key=b"local"),
        )
        expected = hmac.new(b"local", b"data", hashlib.sha256).hexdigest()
        assert client.sign(b"data") == expected
        assert client.degraded is True

    def test_no_fallback_propagates(self) -> None:
        def boom(url: str, payload: bytes, timeout: float) -> str:
            raise ConnectionError("sidecar down")

        client = RemoteSignerClient("http://sidecar/sign", transport=boom)
        with pytest.raises(ConnectionError):
            client.sign(b"data")

    def test_degraded_clears_after_recovery(self) -> None:
        state = {"fail": True}

        def flaky(url: str, payload: bytes, timeout: float) -> str:
            if state["fail"]:
                raise ConnectionError("down")
            return "remote-sig"

        client = RemoteSignerClient(
            "http://sidecar/sign",
            transport=flaky,
            fallback=LocalHmacSigner(key=b"local"),
        )
        client.sign(b"data")
        assert client.degraded is True
        state["fail"] = False
        assert client.sign(b"data") == "remote-sig"
        assert client.degraded is False

    def test_empty_url_rejected(self) -> None:
        with pytest.raises(ValueError):
            RemoteSignerClient("")


class TestResolveAuditSigner:
    def test_default_is_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MAREF_AUDIT_SIGNER_URL", raising=False)
        monkeypatch.delenv("MAREF_TRUST_DOMAIN", raising=False)
        monkeypatch.delenv("MAREF_PRODUCTION", raising=False)
        assert isinstance(resolve_audit_signer(), LocalHmacSigner)

    def test_url_selects_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_AUDIT_SIGNER_URL", "http://sidecar/sign")
        signer = resolve_audit_signer()
        assert isinstance(signer, RemoteSignerClient)
        assert signer.url == "http://sidecar/sign"


class _RecordingSigner:
    backend_name = "recording"
    degraded = False

    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def sign(self, payload: bytes) -> str:
        self.payloads.append(payload)
        return "recorded-signature"


class TestStateMachineWiring:
    def test_state_machine_uses_resolved_signer(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        recorder = _RecordingSigner()
        monkeypatch.setattr(sm_mod, "resolve_audit_signer", lambda: recorder)
        monkeypatch.setenv("MAREF_AUDIT_PATH", str(tmp_path / ".governance"))
        sm = GovernanceStateMachine()
        assert sm.transition(GovernanceState.OBSERVE) is True
        assert recorder.payloads

    def test_missing_key_still_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(sm_mod, "resolve_audit_signer", lambda: LocalHmacSigner(key=b""))
        monkeypatch.setattr(sm_mod, "_write_hmac_missing_alert", lambda: None)
        monkeypatch.setenv("MAREF_AUDIT_PATH", str(tmp_path / ".governance"))
        sm = GovernanceStateMachine()
        with pytest.raises(ValueError, match="fail-closed"):
            sm.transition(GovernanceState.OBSERVE)


class TestTrustDomainEnforcement:
    def test_enforce_requires_remote_signer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_TRUST_DOMAIN", "enforce")
        monkeypatch.delenv("MAREF_AUDIT_SIGNER_URL", raising=False)
        with pytest.raises(AuditKeyMissingError):
            resolve_audit_signer()

    def test_enforce_uses_remote_without_local_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_TRUST_DOMAIN", "enforce")
        monkeypatch.setenv("MAREF_AUDIT_SIGNER_URL", "http://sidecar/sign")
        signer = resolve_audit_signer()
        assert isinstance(signer, RemoteSignerClient)

    def test_production_defaults_to_remote_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MAREF_TRUST_DOMAIN", raising=False)
        monkeypatch.setenv("MAREF_PRODUCTION", "1")
        monkeypatch.delenv("MAREF_AUDIT_SIGNER_URL", raising=False)
        with pytest.raises(AuditKeyMissingError):
            resolve_audit_signer()
