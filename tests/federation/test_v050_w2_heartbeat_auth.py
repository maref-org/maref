"""
v0.50 W2-S1 — 联邦心跳身份认证测试（F12）

覆盖：
- 可配 allowed_heartbeat_servers 白名单，未知 server_id 拒绝 + 审计
- 可选 heartbeat token 校验（X-MAREF-HB-Token）
- 未配置时向后兼容但记 unsecured_heartbeat 审计警告
"""

from __future__ import annotations

from maref.federation.membership import HeartbeatMessage, MembershipManager


class _FakeHealthMonitor:
    def __init__(self) -> None:
        self.probed: list[str] = []

    def member_snapshots(self) -> list[object]:
        return []

    def probe(self, server_id: str) -> None:
        self.probed.append(server_id)


class _FakeDiscovery:
    def __init__(self) -> None:
        self.peers: dict[str, str] = {}

    def list_peers(self) -> list[object]:
        return [type("P", (), {"server_id": k, "endpoint_url": v})() for k, v in self.peers.items()]

    def add_peer(self, server_id: str, endpoint_url: str) -> None:
        self.peers[server_id] = endpoint_url


def _make_manager(**kwargs) -> MembershipManager:
    defaults = {
        "server_id": "org-alpha",
        "endpoint_url": "http://alpha.local",
        "health_monitor": _FakeHealthMonitor(),
        "discovery": _FakeDiscovery(),
    }
    defaults.update(kwargs)
    return MembershipManager(**defaults)


class TestW2S1HeartbeatWhitelist:
    def test_unknown_server_rejected_when_whitelist_configured(self) -> None:
        mgr = _make_manager(allowed_heartbeat_servers={"org-beta"})
        result = mgr.receive_heartbeat(
            HeartbeatMessage(server_id="org-evil", endpoint_url="http://evil.local")
        )
        assert result is False

    def test_unknown_server_not_auto_registered_when_whitelist_configured(self) -> None:
        discovery = _FakeDiscovery()
        mgr = _make_manager(
            allowed_heartbeat_servers={"org-beta"},
            discovery=discovery,
        )
        mgr.receive_heartbeat(
            HeartbeatMessage(server_id="org-evil", endpoint_url="http://evil.local")
        )
        assert "org-evil" not in discovery.peers

    def test_known_server_accepted_when_whitelist_configured(self) -> None:
        discovery = _FakeDiscovery()
        mgr = _make_manager(
            allowed_heartbeat_servers={"org-beta"},
            discovery=discovery,
        )
        result = mgr.receive_heartbeat(
            HeartbeatMessage(server_id="org-beta", endpoint_url="http://beta.local")
        )
        assert result is True
        assert "org-beta" in discovery.peers

    def test_unsecured_heartbeat_recorded_when_no_whitelist(self) -> None:
        mgr = _make_manager()
        warnings: list[dict] = []
        mgr.set_audit_sink(lambda record: warnings.append(record))
        result = mgr.receive_heartbeat(
            HeartbeatMessage(server_id="org-any", endpoint_url="http://any.local")
        )
        assert result is True
        assert any(w.get("event_type") == "unsecured_heartbeat" for w in warnings)

    def test_self_echo_ignored_even_when_whitelist_configured(self) -> None:
        mgr = _make_manager(allowed_heartbeat_servers={"org-alpha"})
        result = mgr.receive_heartbeat(
            HeartbeatMessage(server_id="org-alpha", endpoint_url="http://alpha.local")
        )
        assert result is False


class TestW2S1HeartbeatToken:
    def test_token_mismatch_rejected(self) -> None:
        mgr = _make_manager(heartbeat_token="secret-token")
        result = mgr.receive_heartbeat(
            HeartbeatMessage(server_id="org-beta", endpoint_url="http://beta.local"),
            token="wrong-token",
        )
        assert result is False

    def test_token_match_accepted(self) -> None:
        mgr = _make_manager(heartbeat_token="secret-token")
        result = mgr.receive_heartbeat(
            HeartbeatMessage(server_id="org-beta", endpoint_url="http://beta.local"),
            token="secret-token",
        )
        assert result is True

    def test_token_required_but_missing_rejected(self) -> None:
        mgr = _make_manager(heartbeat_token="secret-token")
        result = mgr.receive_heartbeat(
            HeartbeatMessage(server_id="org-beta", endpoint_url="http://beta.local")
        )
        assert result is False
