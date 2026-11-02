"""入口闸（EntryGate）行为测试。

覆盖：身份缺失/无效、委托链深度/环/能力越级/跳签名/尾节点、消毒命中和
shadow 模式，以及接入 GovernancePipeline 后的拒绝与元数据留痕。
"""

from __future__ import annotations

import json

import pytest

from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    Verdict,
)
from maref.governance.entry_gate import EntryGate
from maref.identity.principal_credential import PrincipalCredential, PrincipalRegistry
from maref.security.trust_chain import DelegationCapability, DelegationChain
from maref.signing.signing_key import ReportSigningKey

HMAC_KEY = b"test-deployment-hmac-key"
PRINCIPAL = "did:principal:alice"


@pytest.fixture
def principal_key() -> ReportSigningKey:
    return ReportSigningKey.generate()


@pytest.fixture
def registry(principal_key: ReportSigningKey) -> PrincipalRegistry:
    registry = PrincipalRegistry()
    registry.register(PRINCIPAL, principal_key.public_key_pem)
    return registry


def _credential(
    key: ReportSigningKey,
    agent: str = "agent-3",
    actions: tuple[str, ...] = ("file.read",),
) -> PrincipalCredential:
    credential = PrincipalCredential.issue(PRINCIPAL, agent, list(actions))
    credential.sign(key)
    return credential


def _chain(
    *agents: str,
    root_principal: str = PRINCIPAL,
    capabilities: tuple[DelegationCapability, ...] = (),
    hmac_key: bytes = HMAC_KEY,
    max_depth: int = 5,
) -> DelegationChain:
    chain = DelegationChain.create_hmac(
        agents[0],
        hmac_key,
        root_principal=root_principal,
        max_depth=max_depth,
    )
    caps = list(capabilities) or [DelegationCapability.DELEGATE] * (len(agents) - 1)
    for parent, child, capability in zip(agents, agents[1:], caps, strict=False):
        assert chain.add_delegation_hmac(parent, child, capability, hmac_key)
    return chain


def _request(
    agent: str = "agent-3",
    action: str = "file.read",
    credential: PrincipalCredential | None = None,
    chain: DelegationChain | None = None,
    intent: str = "",
    principal: str = PRINCIPAL,
) -> GovernanceRequest:
    return GovernanceRequest(
        action=action,
        agent_id=agent,
        principal_did=principal,
        principal_credential=credential.to_dict() if credential else None,
        delegation_chain=chain.to_dict() if chain else None,
        intent=intent,
    )


def _gate(registry: PrincipalRegistry, **overrides) -> EntryGate:
    options = {
        "principal_registry": registry,
        "hmac_keys": [HMAC_KEY],
        "max_depth": 5,
    }
    options.update(overrides)
    return EntryGate(**options)


class TestIdentityGate:
    def test_missing_agent_id_denied(self, registry):
        gate = _gate(registry)
        decision = gate.evaluate(_request(agent=""))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:identity_missing"

    def test_missing_principal_credential_denied(self, registry):
        gate = _gate(registry)
        decision = gate.evaluate(_request())
        assert decision.blocking is True
        assert decision.rule == "entry_gate:identity_missing"

    def test_valid_credential_allowed(self, registry, principal_key):
        gate = _gate(registry)
        decision = gate.evaluate(_request(credential=_credential(principal_key)))
        assert decision.allowed is True
        assert decision.root_principal == PRINCIPAL

    def test_unknown_principal_denied(self, registry, principal_key):
        gate = _gate(registry)
        credential = _credential(principal_key)
        decision = gate.evaluate(_request(credential=credential, principal="did:principal:mallory"))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:identity_invalid"

    def test_credential_bound_to_other_agent_denied(self, registry, principal_key):
        gate = _gate(registry)
        credential = _credential(principal_key, agent="agent-other")
        decision = gate.evaluate(_request(credential=credential))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:identity_invalid"

    def test_forged_credential_signature_denied(self, registry, principal_key):
        gate = _gate(registry)
        credential = _credential(principal_key)
        credential.sign(ReportSigningKey.generate())
        decision = gate.evaluate(_request(credential=credential))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:identity_invalid"

    def test_action_outside_scope_denied(self, registry, principal_key):
        gate = _gate(registry)
        credential = _credential(principal_key, actions=("file.read",))
        decision = gate.evaluate(_request(action="shell.exec", credential=credential))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:identity_invalid"


class TestDelegationGate:
    def test_three_hop_chain_allowed_and_traceable(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain(
            "agent-1",
            "agent-2",
            "agent-3",
            capabilities=(DelegationCapability.DELEGATE, DelegationCapability.READ),
        )
        decision = gate.evaluate(_request(credential=_credential(principal_key), chain=chain))
        assert decision.allowed is True
        assert decision.root_principal == PRINCIPAL
        assert decision.chain_digest

    def test_required_chain_missing_denied(self, registry, principal_key):
        gate = _gate(registry, require_delegation=True)
        decision = gate.evaluate(_request(credential=_credential(principal_key)))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_missing"

    def test_depth_exceeded_denied(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain("agent-1", "agent-2", "agent-3")
        data = chain.to_dict()
        data["max_depth"] = 2
        request = _request(credential=_credential(principal_key))
        request.delegation_chain = data
        decision = gate.evaluate(request)
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_depth"

    def test_cycle_denied(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain("agent-1", "agent-2", "agent-3")
        data = chain.to_dict()
        data["nodes"][2]["agent_id"] = "agent-2"
        request = _request(credential=_credential(principal_key))
        request.delegation_chain = data
        decision = gate.evaluate(request)
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_cycle"

    def test_capability_escalation_denied(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain("agent-1", "agent-2", "agent-3")
        data = chain.to_dict()
        data["nodes"][2]["capability"] = DelegationCapability.ADMIN.value
        request = _request(credential=_credential(principal_key))
        request.delegation_chain = data
        decision = gate.evaluate(request)
        assert decision.blocking is True
        assert decision.rule == "entry_gate:capability_escalation"

    def test_hmac_signature_mismatch_denied(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain("agent-1", "agent-2", "agent-3")
        data = chain.to_dict()
        # 只改被签名覆盖、但不破坏结构连续性的字段。
        data["nodes"][1]["timestamp"] = "2020-01-01T00:00:00+00:00"
        request = _request(credential=_credential(principal_key))
        request.delegation_chain = data
        decision = gate.evaluate(request)
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_signature"

    def test_hmac_key_missing_denied(self, registry, principal_key):
        gate = _gate(registry, hmac_keys=[])
        chain = _chain("agent-1", "agent-2", "agent-3")
        decision = gate.evaluate(_request(credential=_credential(principal_key), chain=chain))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_signature"

    def test_tampered_depth_field_cannot_bypass_validation(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain("agent-1", "agent-2", "agent-3")
        data = chain.to_dict()
        # depth 不在 HMAC 载荷内，篡改后应被节点数推导覆盖。
        data["depth"] = 1
        data["max_depth"] = 2
        request = _request(credential=_credential(principal_key))
        request.delegation_chain = data
        decision = gate.evaluate(request)
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_depth"

    def test_actual_depth_exceeds_gate_limit_denied(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain(
            "agent-1",
            "agent-2",
            "agent-3",
            "agent-4",
            "agent-5",
            "agent-6",
            max_depth=10,
        )
        decision = gate.evaluate(
            _request(
                agent="agent-6",
                credential=_credential(principal_key, agent="agent-6"),
                chain=chain,
            )
        )
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_depth"

    def test_unsigned_chain_denied(self, registry, principal_key):
        gate = _gate(registry)
        chain = DelegationChain.create("agent-3")
        chain.root_principal = PRINCIPAL
        decision = gate.evaluate(
            _request(credential=_credential(principal_key), chain=chain)
        )
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_signature"

    def test_requester_not_chain_tail_denied(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain("agent-1", "agent-2")
        decision = gate.evaluate(
            _request(agent="agent-3", credential=None, chain=chain)
        )
        # 无身份凭证时先命中身份缺失；补齐身份后验证尾节点规则。
        assert decision.blocking is True
        credential = _credential(principal_key)
        decision = gate.evaluate(_request(agent="agent-3", credential=credential, chain=chain))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:delegation_tail"

    def test_root_principal_mismatch_denied(self, registry, principal_key):
        gate = _gate(registry)
        chain = _chain("agent-1", "agent-2", "agent-3", root_principal="did:principal:other")
        decision = gate.evaluate(_request(credential=_credential(principal_key), chain=chain))
        assert decision.blocking is True
        assert decision.rule == "entry_gate:root_principal"


class TestSanitizerGate:
    def test_pii_flagged_but_allowed(self, registry, principal_key):
        gate = _gate(registry)
        decision = gate.evaluate(
            _request(credential=_credential(principal_key), intent="contact bob@example.com")
        )
        assert decision.allowed is True
        assert "pii:email" in decision.detections
        assert decision.sanitized_intent and "bob@example.com" not in decision.sanitized_intent

    def test_sql_injection_content_denied(self, registry, principal_key):
        gate = _gate(registry)
        decision = gate.evaluate(
            _request(
                credential=_credential(principal_key),
                intent="'; DROP TABLE users; --",
            )
        )
        assert decision.blocking is True
        assert decision.rule == "entry_gate:unsafe_content"

    def test_shadow_mode_reports_without_blocking(self, registry, principal_key):
        gate = _gate(registry, shadow=True)
        decision = gate.evaluate(
            _request(
                credential=_credential(principal_key),
                intent="'; DROP TABLE users; --",
            )
        )
        assert decision.allowed is False
        assert decision.blocking is False
        assert gate.shadow is True


class TestPipelineIntegration:
    def test_pipeline_without_gate_unchanged(self):
        pipeline = GovernancePipeline()
        result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test"))
        assert result.verdict == Verdict.ALLOW

    def test_pipeline_denies_when_entry_gate_blocks(self, registry):
        pipeline = GovernancePipeline(entry_gate=_gate(registry))
        result = pipeline.govern(_request())
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "entry_gate:identity_missing"

    def test_pipeline_allows_and_records_entry_metadata(self, registry, principal_key):
        pipeline = GovernancePipeline(entry_gate=_gate(registry))
        chain = _chain("agent-1", "agent-2", "agent-3")
        result = pipeline.govern(
            _request(credential=_credential(principal_key), chain=chain)
        )
        assert result.verdict == Verdict.ALLOW
        assert result.entry_root_principal == PRINCIPAL
        assert result.entry_chain_digest

    def test_pipeline_shadow_mode_does_not_deny(self, registry, principal_key):
        pipeline = GovernancePipeline(entry_gate=_gate(registry, shadow=True))
        result = pipeline.govern(
            _request(
                credential=_credential(principal_key),
                intent="'; DROP TABLE users; --",
            )
        )
        assert result.verdict == Verdict.ALLOW
        assert result.entry_detections


class TestGovernedPipelineWiring:
    def _governed(self, tmp_path, entry_gate=None):
        from maref.governance.governed_pipeline import GovernedPipeline

        return GovernedPipeline(
            audit_path=tmp_path / "audit.jsonl",
            hmac_key="test-key",
            entry_gate=entry_gate,
        )

    def test_disabled_by_default(self, tmp_path):
        pipeline = self._governed(tmp_path)
        assert pipeline.entry_gate is None
        result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test"))
        assert result.verdict == Verdict.ALLOW

    def test_entry_gate_denies_and_writes_audit(self, tmp_path, registry):
        pipeline = self._governed(tmp_path, entry_gate=_gate(registry))
        result = pipeline.govern(_request())
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "entry_gate:identity_missing"

    def test_entry_metadata_reaches_audit_log(self, tmp_path, registry, principal_key):
        pipeline = self._governed(tmp_path, entry_gate=_gate(registry))
        chain = _chain("agent-1", "agent-2", "agent-3")
        result = pipeline.govern(
            _request(credential=_credential(principal_key), chain=chain)
        )
        assert result.verdict == Verdict.ALLOW
        events = [
            json.loads(line)
            for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert events
        assert events[-1]["metadata"]["entry_root_principal"] == PRINCIPAL
        assert events[-1]["metadata"]["entry_chain_digest"]

    def test_original_intent_preserved_and_hashed(self, tmp_path, registry, principal_key):
        import hashlib

        pipeline = self._governed(tmp_path, entry_gate=_gate(registry))
        request = _request(
            credential=_credential(principal_key), intent="contact bob@example.com"
        )
        result = pipeline.govern(request)
        assert result.verdict == Verdict.ALLOW
        assert request.intent == "contact bob@example.com"
        events = [
            json.loads(line)
            for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert events[-1]["metadata"]["intent_hash"] == hashlib.sha256(
            request.intent.encode("utf-8")
        ).hexdigest()
        assert "bob@example.com" not in json.dumps(events[-1], ensure_ascii=False)

    def test_env_enable_without_registry_fails_closed(self, tmp_path, monkeypatch):
        from maref.governance.governed_pipeline import GovernedPipeline

        monkeypatch.setenv("MAREF_ENTRY_GATE", "1")
        monkeypatch.delenv("MAREF_PRINCIPAL_REGISTRY", raising=False)
        with pytest.raises(ValueError):
            GovernedPipeline(
                audit_path=tmp_path / "audit.jsonl",
                hmac_key="test-key",
            )
