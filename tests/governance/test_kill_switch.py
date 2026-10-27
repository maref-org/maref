"""Kill switch：三级停机、递归子智能体与带外解除授权测试。"""

from __future__ import annotations

import json
import time
from dataclasses import replace

import pytest

from maref.governance.core_pipeline import GovernanceRequest, Verdict
from maref.governance.kill_switch import (
    DisengageAuthorization,
    KillScope,
    KillSwitch,
    KillSwitchAuthorizationError,
)
from maref.signing.signing_key import ReportSigningKey

ACTOR = "ops:commander"
TENANT = "acme"
PARENT = "agent-parent"
CHILD = "agent-child"
GRANDCHILD = "agent-grandchild"


@pytest.fixture
def commander_key() -> ReportSigningKey:
    return ReportSigningKey.generate()


@pytest.fixture
def switch(commander_key: ReportSigningKey) -> KillSwitch:
    return KillSwitch(authorizer_keys={ACTOR: commander_key.public_key_pem})


def _authorization(
    key: ReportSigningKey,
    scope: KillScope,
    target: str,
    *,
    actor: str = ACTOR,
    issued_at: float | None = None,
    nonce: str = "nonce-1",
) -> DisengageAuthorization:
    authorization = DisengageAuthorization(
        actor=actor,
        scope=scope.value,
        target=target,
        issued_at=time.time() if issued_at is None else issued_at,
        nonce=nonce,
        signature="",
    )
    return replace(
        authorization, signature=key.sign_report(authorization.payload())
    )


class TestKillScopes:
    def test_global_engage_blocks_everything(self, switch: KillSwitch):
        switch.engage(KillScope.GLOBAL, "", "incident", ACTOR)
        assert switch.blocked_scope(TENANT, "agent-x") == "global"
        assert switch.is_blocked("", "agent-y") is True

    def test_tenant_engage_blocks_only_that_tenant(self, switch: KillSwitch):
        switch.engage(KillScope.TENANT, TENANT, "incident", ACTOR)
        assert switch.blocked_scope(TENANT, "agent-x") == "tenant"
        assert switch.is_blocked("other-tenant", "agent-x") is False

    def test_agent_engage_recursively_blocks_children(self, switch: KillSwitch):
        switch.register_child(PARENT, CHILD)
        switch.register_child(CHILD, GRANDCHILD)

        switch.engage(KillScope.AGENT, PARENT, "runaway", ACTOR)

        assert switch.is_blocked("", PARENT) is True
        assert switch.is_blocked("", CHILD) is True
        assert switch.is_blocked("", GRANDCHILD) is True
        assert switch.is_blocked("", "agent-unrelated") is False

    def test_child_registered_after_engage_is_blocked(self, switch: KillSwitch):
        switch.engage(KillScope.AGENT, PARENT, "runaway", ACTOR)
        switch.register_child(PARENT, "agent-late")
        assert switch.is_blocked("", "agent-late") is True

    def test_block_hook_receives_descendants(self, switch: KillSwitch):
        seen: list[str] = []
        switch.add_block_hook(lambda agent_id, reason, actor: seen.append(agent_id))
        switch.register_child(PARENT, CHILD)
        switch.register_child(CHILD, GRANDCHILD)

        switch.engage(KillScope.AGENT, PARENT, "runaway", ACTOR)

        assert set(seen) == {PARENT, CHILD, GRANDCHILD}

    def test_invalid_scope_rejected(self, switch: KillSwitch):
        with pytest.raises(ValueError):
            switch.engage("cluster", "x", "incident", ACTOR)
        with pytest.raises(ValueError):
            switch.engage(KillScope.AGENT, "", "incident", ACTOR)


class TestEngageAndDisengage:
    def test_signed_authorization_releases_agent(
        self, switch: KillSwitch, commander_key: ReportSigningKey
    ):
        switch.engage(KillScope.AGENT, PARENT, "runaway", ACTOR)
        authorization = _authorization(commander_key, KillScope.AGENT, PARENT)

        assert switch.disengage(KillScope.AGENT, PARENT, "resolved", ACTOR, authorization)
        assert switch.is_blocked("", PARENT) is False

    def test_signed_authorization_disengages_tenant(
        self, switch: KillSwitch, commander_key: ReportSigningKey
    ):
        switch.engage(KillScope.TENANT, TENANT, "incident", ACTOR)
        authorization = _authorization(commander_key, KillScope.TENANT, TENANT)

        assert switch.disengage(KillScope.TENANT, TENANT, "resolved", ACTOR, authorization)
        assert switch.is_blocked(TENANT, "agent-x") is False

    def test_signed_authorization_disengages_global(
        self, switch: KillSwitch, commander_key: ReportSigningKey
    ):
        switch.engage(KillScope.GLOBAL, "", "incident", ACTOR)
        authorization = _authorization(commander_key, KillScope.GLOBAL, "*")

        assert switch.disengage(KillScope.GLOBAL, "", "resolved", ACTOR, authorization)
        assert switch.is_blocked("", "agent-x") is False

    def test_forged_authorization_rejected(
        self, switch: KillSwitch
    ):
        switch.engage(KillScope.AGENT, PARENT, "runaway", ACTOR)
        forged = _authorization(ReportSigningKey.generate(), KillScope.AGENT, PARENT)

        with pytest.raises(KillSwitchAuthorizationError):
            switch.disengage(KillScope.AGENT, PARENT, "resolved", ACTOR, forged)
        assert switch.is_blocked("", PARENT) is True

    def test_missing_authorization_rejected(self, switch: KillSwitch):
        switch.engage(KillScope.AGENT, PARENT, "runaway", ACTOR)
        with pytest.raises(KillSwitchAuthorizationError):
            switch.disengage(KillScope.AGENT, PARENT, "resolved", ACTOR, None)

    def test_scope_mismatch_rejected(
        self, switch: KillSwitch, commander_key: ReportSigningKey
    ):
        switch.engage(KillScope.TENANT, TENANT, "runaway", ACTOR)
        authorization = _authorization(commander_key, KillScope.AGENT, PARENT)

        with pytest.raises(KillSwitchAuthorizationError):
            switch.disengage(KillScope.TENANT, TENANT, "resolved", ACTOR, authorization)
        assert switch.is_blocked(TENANT, "agent-x") is True

    def test_replayed_authorization_rejected(
        self, switch: KillSwitch, commander_key: ReportSigningKey
    ):
        switch.engage(KillScope.AGENT, PARENT, "runaway", ACTOR)
        authorization = _authorization(commander_key, KillScope.AGENT, PARENT)
        assert switch.disengage(KillScope.AGENT, PARENT, "resolved", ACTOR, authorization)

        with pytest.raises(KillSwitchAuthorizationError):
            switch.disengage(KillScope.AGENT, PARENT, "resolved", ACTOR, authorization)

    def test_expired_authorization_rejected(
        self, switch: KillSwitch, commander_key: ReportSigningKey
    ):
        switch.engage(KillScope.AGENT, PARENT, "runaway", ACTOR)
        authorization = _authorization(
            commander_key,
            KillScope.AGENT,
            PARENT,
            issued_at=time.time() - 3600,
        )

        with pytest.raises(KillSwitchAuthorizationError):
            switch.disengage(KillScope.AGENT, PARENT, "resolved", ACTOR, authorization)


class TestStateMachineHook:
    def test_global_engage_halts_state_machine(self):
        class _Recorder:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def force_halt(self, reason: str = "", actor: str = "") -> bool:
                self.calls.append((reason, actor))
                return True

        recorder = _Recorder()
        switch = KillSwitch(state_machine=recorder)

        switch.engage(KillScope.GLOBAL, "", "incident", ACTOR)

        assert recorder.calls
        assert "incident" in recorder.calls[0][0]
        assert recorder.calls[0][1] == ACTOR


class TestPipelineIntegration:
    @staticmethod
    def _pipeline(tmp_path, switch: KillSwitch):
        from maref.governance.governed_pipeline import GovernedPipeline

        return GovernedPipeline(
            audit_path=tmp_path / "audit.jsonl",
            hmac_key="test-key",
            kill_switch=switch,
        )

    def test_agent_blocked_denied_by_pipeline(self, tmp_path, switch: KillSwitch):
        switch.engage(KillScope.AGENT, "agent-a", "runaway", ACTOR)
        pipeline = self._pipeline(tmp_path, switch)

        result = pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a")
        )

        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "kill_switch:agent"

    def test_tenant_blocked_denied_by_pipeline(self, tmp_path, switch: KillSwitch):
        switch.engage(KillScope.TENANT, TENANT, "incident", ACTOR)
        pipeline = self._pipeline(tmp_path, switch)

        result = pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a", tenant_id=TENANT)
        )

        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "kill_switch:tenant"

    def test_kill_switch_events_reach_audit_log(self, tmp_path, switch: KillSwitch):
        pipeline = self._pipeline(tmp_path, switch)
        switch.engage(KillScope.AGENT, "agent-a", "runaway", ACTOR)
        pipeline.govern(GovernanceRequest(action="file.read", agent_id="agent-a"))

        events = [
            json.loads(line)
            for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(event["event_type"] == "kill_switch.engage" for event in events)
        assert events[-1]["metadata"]["matched_rule"] == "kill_switch:agent"

    @pytest.mark.parametrize(
        ("action", "parameters"),
        [
            ("kill_switch.disengage", {}),
            (
                "governance.disengage",
                {"disengage": True, "scope": "agent", "target": "agent-a"},
            ),
        ],
    )
    def test_agent_cannot_disengage_through_requests(
        self, tmp_path, switch: KillSwitch, action, parameters
    ):
        switch.engage(KillScope.AGENT, "agent-a", "runaway", ACTOR)
        pipeline = self._pipeline(tmp_path, switch)

        result = pipeline.govern(
            GovernanceRequest(action=action, agent_id="agent-a", parameters=parameters)
        )

        assert result.verdict == Verdict.DENY
        assert switch.is_blocked("", "agent-a") is True
        assert not hasattr(pipeline, "disengage")

    def test_default_pipeline_has_unblocked_switch(self, tmp_path):
        from maref.governance.governed_pipeline import GovernedPipeline

        pipeline = GovernedPipeline(
            audit_path=tmp_path / "audit.jsonl", hmac_key="test-key"
        )
        assert pipeline.kill_switch.is_blocked("", "agent-a") is False
        result = pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        )
        assert result.verdict == Verdict.ALLOW
