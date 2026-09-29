"""CredentialBroker 单元测试 — 凭证代理 (P1-7)."""

from __future__ import annotations

import pytest

from maref.governance.credential_broker import (
    CredentialBroker,
    CredentialError,
    DictKeyProvider,
    build_broker_from_env,
    get_default_broker,
    is_placeholder,
    placeholder_for,
    resolve_credential,
    set_default_broker,
)


@pytest.fixture(autouse=True)
def _reset_broker() -> None:
    set_default_broker(None)
    yield
    set_default_broker(None)


def _broker(presented_ok: bool = True) -> CredentialBroker:
    return CredentialBroker(
        endpoints={"openai": ["api.openai.com"]},
        key_names={"openai": "OPENAI_API_KEY"},
        key_provider=DictKeyProvider({"OPENAI_API_KEY": "sk-real-secret"}),
    )


class TestPlaceholders:
    def test_is_placeholder(self) -> None:
        assert is_placeholder(placeholder_for("openai")) is True
        assert is_placeholder("sk-real") is False
        assert is_placeholder(None) is False

    def test_placeholder_for(self) -> None:
        assert placeholder_for("openai") == "MAREF_PLACEHOLDER_openai"


class TestBrokerResolve:
    def test_injects_real_key_for_allowlisted_endpoint(self) -> None:
        broker = _broker()
        key = broker.resolve("openai", "https://api.openai.com/v1", placeholder_for("openai"))
        assert key == "sk-real-secret"

    def test_injects_when_no_presented_value(self) -> None:
        broker = _broker()
        assert broker.resolve("openai", "https://api.openai.com/v1") == "sk-real-secret"

    def test_subdomain_allowed(self) -> None:
        broker = _broker()
        assert broker.endpoint_allowed("openai", "https://eu.api.openai.com/v1") is True

    def test_non_allowlisted_endpoint_rejected(self) -> None:
        broker = _broker()
        with pytest.raises(CredentialError, match="not allowlisted"):
            broker.resolve("openai", "https://evil.example.com/v1")

    def test_unknown_service_rejected(self) -> None:
        broker = _broker()
        with pytest.raises(CredentialError, match="unknown service"):
            broker.resolve("mystery", "https://api.openai.com/v1")

    def test_missing_key_rejected(self) -> None:
        broker = CredentialBroker(
            endpoints={"openai": ["api.openai.com"]},
            key_names={"openai": "OPENAI_API_KEY"},
            key_provider=DictKeyProvider({}),
        )
        with pytest.raises(CredentialError, match="no credential"):
            broker.resolve("openai", "https://api.openai.com/v1")

    def test_agent_presenting_real_key_rejected(self) -> None:
        broker = _broker()
        with pytest.raises(CredentialError, match="placeholder"):
            broker.resolve("openai", "https://api.openai.com/v1", "sk-leaked")

    def test_disabled_broker_returns_presented(self) -> None:
        broker = _broker()
        broker.enabled = False
        assert broker.resolve("openai", "https://evil.example.com", "sk-x") == "sk-x"

    def test_to_dict(self) -> None:
        payload = _broker().to_dict()
        assert payload["services"] == ["openai"]
        assert payload["endpoints"] == {"openai": ["api.openai.com"]}


class TestResolveCredential:
    def test_legacy_without_broker_returns_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        assert resolve_credential("openai", "OPENAI_API_KEY", "https://api.openai.com") == "sk-env"

    def test_legacy_without_broker_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert resolve_credential("openai", "OPENAI_API_KEY", "https://api.openai.com") == ""

    def test_presented_wins_without_broker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert (
            resolve_credential("openai", "OPENAI_API_KEY", "https://api.openai.com", "sk-arg")
            == "sk-arg"
        )

    def test_broker_injects_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        set_default_broker(_broker())
        monkeypatch.setenv("OPENAI_API_KEY", placeholder_for("openai"))
        assert (
            resolve_credential("openai", "OPENAI_API_KEY", "https://api.openai.com/v1")
            == "sk-real-secret"
        )

    def test_broker_rejects_env_real_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        set_default_broker(_broker())
        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        with pytest.raises(CredentialError):
            resolve_credential("openai", "OPENAI_API_KEY", "https://api.openai.com/v1")


class TestBuildFromEnv:
    def test_disabled_returns_none(self) -> None:
        assert build_broker_from_env({}) is None

    def test_enabled_builds_broker(self) -> None:
        env = {
            "MAREF_CREDENTIAL_BROKER": "1",
            "MAREF_BROKER_ENDPOINTS": '{"openai": ["api.openai.com"]}',
            "MAREF_BROKER_KEY_NAMES": '{"openai": "OPENAI_API_KEY"}',
        }
        broker = build_broker_from_env(env)
        assert broker is not None
        assert broker.endpoints == {"openai": ["api.openai.com"]}
        assert broker.key_names == {"openai": "OPENAI_API_KEY"}
        assert get_default_broker() is None  # build does not auto-install

    def test_set_and_get_default(self) -> None:
        broker = _broker()
        set_default_broker(broker)
        assert get_default_broker() is broker
