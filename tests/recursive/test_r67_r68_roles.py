from __future__ import annotations

import time

import pytest

from maref.recursive.role_composer import (
    DEAD_ZONE_HEXAGRAMS,
    HexagramWorkflow,
    RoleComposer,
)
from maref.recursive.role_lifecycle import (
    RoleLifecycle,
    RoleLifecycleState,
    RolePhase,
)
from maref.recursive.role_registry import (
    PluginRole,
    PluginRoleCapability,
    PluginRoleIdentity,
    PluginRoleTrust,
    RoleRegistry,
    parse_role_from_dict,
    validate_role,
)

VALID_ROLE_DICT = {
    "maref_role": "1.0",
    "identity": {
        "did": "did:maref:plugin/code-reviewer/v1",
        "name": "code-reviewer",
        "version": "1.0.0",
    },
    "capability": {
        "trigram": "离",
        "allowed_tools": ["review", "lint", "validate"],
        "denied_tools": [],
        "max_entropy": 4.0,
    },
    "trust": {
        "min_trust_score": 0.6,
        "require_did": True,
        "require_vc": False,
    },
    "lifecycle": {},
}


class TestRoleValidation:
    def test_valid_role_passes(self) -> None:
        role = parse_role_from_dict(VALID_ROLE_DICT)
        errors = validate_role(role)
        assert len(errors) == 0

    def test_invalid_maref_role_version(self) -> None:
        data = {**VALID_ROLE_DICT, "maref_role": "0.5"}
        role = parse_role_from_dict(data)
        errors = validate_role(role)
        assert any("maref_role" in e for e in errors)

    def test_missing_did(self) -> None:
        data = {**VALID_ROLE_DICT}
        data["identity"] = {**data["identity"], "did": ""}
        role = parse_role_from_dict(data)
        errors = validate_role(role)
        assert any("did" in e for e in errors)

    def test_invalid_did_format(self) -> None:
        data = {**VALID_ROLE_DICT}
        data["identity"] = {**data["identity"], "did": "invalid-format"}
        role = parse_role_from_dict(data)
        errors = validate_role(role)
        assert any("did:" in e for e in errors)

    def test_invalid_trigram(self) -> None:
        data = {**VALID_ROLE_DICT}
        data["capability"] = {**data["capability"], "trigram": "X"}
        role = parse_role_from_dict(data)
        errors = validate_role(role)
        assert any("trigram" in e for e in errors)

    def test_tool_conflict_allowed_denied(self) -> None:
        data = {**VALID_ROLE_DICT}
        data["capability"] = {
            "trigram": "坎",
            "allowed_tools": ["search", "lint"],
            "denied_tools": ["lint", "delete"],
            "max_entropy": 5.0,
        }
        role = parse_role_from_dict(data)
        errors = validate_role(role)
        assert any("Tool conflict" in e for e in errors)

    def test_negative_max_entropy(self) -> None:
        data = {**VALID_ROLE_DICT}
        data["capability"] = {**data["capability"], "max_entropy": -1.0}
        role = parse_role_from_dict(data)
        errors = validate_role(role)
        assert any("max_entropy" in e for e in errors)

    def test_invalid_trust_score(self) -> None:
        data = {**VALID_ROLE_DICT}
        data["trust"] = {"min_trust_score": 1.5, "require_did": True, "require_vc": False}
        role = parse_role_from_dict(data)
        errors = validate_role(role)
        assert any("min_trust_score" in e for e in errors)

    def test_all_trigrams_valid(self) -> None:
        for trigram in ["乾", "坤", "震", "巽", "坎", "离", "艮", "兑"]:
            data = {**VALID_ROLE_DICT}
            data["capability"] = {**data["capability"], "trigram": trigram}
            role = parse_role_from_dict(data)
            errors = validate_role(role)
            assert len(errors) == 0, f"Trigram {trigram} should be valid"


class TestRoleRegistry:
    def test_register_role(self) -> None:
        role = parse_role_from_dict(VALID_ROLE_DICT)
        registry = RoleRegistry()
        did = registry.register(role)
        assert did == "did:maref:plugin/code-reviewer/v1"

    def test_register_invalid_raises(self) -> None:
        data = {**VALID_ROLE_DICT, "maref_role": "0.5"}
        role = parse_role_from_dict(data)
        registry = RoleRegistry()
        with pytest.raises(ValueError, match="Role validation failed"):
            registry.register(role)

    def test_register_from_dict(self) -> None:
        registry = RoleRegistry()
        did = registry.register_from_dict(VALID_ROLE_DICT)
        found = registry.get(did)
        assert found is not None
        assert found.identity.name == "code-reviewer"

    def test_get_nonexistent(self) -> None:
        registry = RoleRegistry()
        assert registry.get("did:nonexistent") is None

    def test_list_available(self) -> None:
        registry = RoleRegistry()
        registry.register_from_dict(VALID_ROLE_DICT)
        available = registry.list_available()
        assert len(available) == 1
        assert available[0]["trigram"] == "离"

    def test_remove_role(self) -> None:
        registry = RoleRegistry()
        did = registry.register_from_dict(VALID_ROLE_DICT)
        assert registry.remove(did)
        assert registry.get(did) is None

    def test_remove_nonexistent(self) -> None:
        registry = RoleRegistry()
        assert not registry.remove("did:nonexistent")


class TestRoleLifecycle:
    def test_initial_phase_is_registered(self) -> None:
        lifecycle = RoleLifecycle()
        assert lifecycle.phase == RolePhase.REGISTERED

    def test_promote_to_sandbox(self) -> None:
        lifecycle = RoleLifecycle()
        ok, msg = lifecycle.promote()
        assert ok
        assert lifecycle.phase == RolePhase.SANDBOX

    def test_promote_sandbox_to_shadow_needs_48h(self) -> None:
        lifecycle = RoleLifecycle()
        lifecycle.promote()
        ok, msg = lifecycle.promote()
        assert not ok
        assert "48h" in msg

    def test_promote_sandbox_to_shadow_after_48h(self) -> None:
        state = RoleLifecycleState(
            phase=RolePhase.SANDBOX,
            sandbox_started_at=time.time() - (49 * 3600),
        )
        lifecycle = RoleLifecycle(state)
        ok, msg = lifecycle.promote()
        assert ok
        assert lifecycle.phase == RolePhase.SHADOW

    def test_promote_sandbox_to_shadow_with_incidents(self) -> None:
        state = RoleLifecycleState(
            phase=RolePhase.SANDBOX,
            sandbox_started_at=time.time() - (49 * 3600),
            safety_incidents=1,
        )
        lifecycle = RoleLifecycle(state)
        ok, msg = lifecycle.promote()
        assert not ok
        assert "safety incidents" in msg

    def test_promote_shadow_to_stable_needs_168h(self) -> None:
        state = RoleLifecycleState(
            phase=RolePhase.SHADOW,
            shadow_started_at=time.time() - (100 * 3600),
        )
        lifecycle = RoleLifecycle(state)
        ok, msg = lifecycle.promote()
        assert not ok

    def test_promote_shadow_to_stable_after_168h_with_human_approval(self) -> None:
        state = RoleLifecycleState(
            phase=RolePhase.SHADOW,
            shadow_started_at=time.time() - (169 * 3600),
            human_approved=True,
        )
        lifecycle = RoleLifecycle(state)
        ok, msg = lifecycle.promote()
        assert ok
        assert lifecycle.phase == RolePhase.STABLE

    def test_promote_shadow_to_stable_no_human_approval(self) -> None:
        state = RoleLifecycleState(
            phase=RolePhase.SHADOW,
            shadow_started_at=time.time() - (169 * 3600),
        )
        lifecycle = RoleLifecycle(state)
        ok, msg = lifecycle.promote()
        assert not ok
        assert "Human Gate" in msg

    def test_demote_stable_to_shadow_on_safety(self) -> None:
        state = RoleLifecycleState(
            phase=RolePhase.STABLE,
            stable_at=time.time(),
        )
        lifecycle = RoleLifecycle(state)
        ok, msg = lifecycle.demote("safety_incident")
        assert ok
        assert lifecycle.phase == RolePhase.SHADOW

    def test_demote_shadow_to_sandbox_on_safety(self) -> None:
        state = RoleLifecycleState(phase=RolePhase.SHADOW)
        lifecycle = RoleLifecycle(state)
        ok, msg = lifecycle.demote("safety_incident")
        assert ok
        assert lifecycle.phase == RolePhase.SANDBOX

    def test_revoke_on_three_consecutive_trust_failures(self) -> None:
        lifecycle = RoleLifecycle()
        lifecycle._state.current_trust_score = 0.1
        for _i in range(3):
            ok, msg = lifecycle.handle_trust_below_threshold(0.5)
        assert lifecycle.phase == RolePhase.REVOKED

    def test_trust_ok_resets_failure_count(self) -> None:
        lifecycle = RoleLifecycle()
        lifecycle._state.current_trust_score = 0.0
        lifecycle._state.consecutive_trust_failures = 2
        lifecycle._state.current_trust_score = 0.8
        ok, msg = lifecycle.handle_trust_below_threshold(0.5)
        assert lifecycle._state.consecutive_trust_failures == 0

    def test_deprecate_stable(self) -> None:
        state = RoleLifecycleState(phase=RolePhase.STABLE)
        lifecycle = RoleLifecycle(state)
        ok, msg = lifecycle.deprecate()
        assert ok
        assert lifecycle.phase == RolePhase.DEPRECATED

    def test_revoke_from_any(self) -> None:
        lifecycle = RoleLifecycle()
        ok, msg = lifecycle.revoke()
        assert ok
        assert lifecycle.phase == RolePhase.REVOKED

    def test_full_promotion_path(self) -> None:
        state = RoleLifecycleState(
            phase=RolePhase.SANDBOX,
            sandbox_started_at=time.time() - (49 * 3600),
        )
        lifecycle = RoleLifecycle(state)
        ok1, _ = lifecycle.promote()
        assert ok1
        assert lifecycle.phase == RolePhase.SHADOW

        lifecycle._state.shadow_started_at = time.time() - (169 * 3600)
        lifecycle.human_approve()
        ok2, _ = lifecycle.promote()
        assert ok2
        assert lifecycle.phase == RolePhase.STABLE

    def test_record_safety_incident(self) -> None:
        lifecycle = RoleLifecycle()
        lifecycle.record_safety_incident()
        assert lifecycle._state.safety_incidents == 1


class TestRoleComposer:
    def test_core_without_plugins(self) -> None:
        core = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(
                did="did:maref:core/executor/v1", name="executor", version="1.0"
            ),
            capability=PluginRoleCapability(
                trigram="震", allowed_tools=["write", "edit"], denied_tools=["rm"]
            ),
            trust=PluginRoleTrust(min_trust_score=0.5),
        )
        result = RoleComposer.compose(core, [])
        assert isinstance(result, HexagramWorkflow)
        assert result.role_name == "executor"
        assert result.hexagram not in DEAD_ZONE_HEXAGRAMS

    def test_core_with_one_plugin(self) -> None:
        core = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(
                did="did:maref:core/executor/v1", name="executor", version="1.0"
            ),
            capability=PluginRoleCapability(
                trigram="震",
                allowed_tools=["write", "edit", "run", "test"],
                denied_tools=["rm"],
                max_entropy=12.0,
            ),
            trust=PluginRoleTrust(min_trust_score=0.5),
        )
        plugin = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(
                did="did:maref:plugin/security/v1", name="security-expert", version="1.0"
            ),
            capability=PluginRoleCapability(trigram="艮", allowed_tools=["audit"], denied_tools=[]),
            trust=PluginRoleTrust(min_trust_score=0.6),
        )
        result = RoleComposer.compose(core, [plugin])
        assert isinstance(result, HexagramWorkflow)
        assert not any(t == "rm" for t in result.tools)

    def test_plugin_entropy_exceeds_core(self) -> None:
        core = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(
                did="did:maref:core/executor/v1", name="executor", version="1.0"
            ),
            capability=PluginRoleCapability(trigram="坤", allowed_tools=["do"], max_entropy=1.0),
            trust=PluginRoleTrust(),
        )
        plugin = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(did="did:maref:plugin/big/v1", name="big", version="1.0"),
            capability=PluginRoleCapability(trigram="艮", allowed_tools=["x"], max_entropy=100.0),
            trust=PluginRoleTrust(),
        )
        result = RoleComposer.compose(core, [plugin])
        from maref.recursive.role_composer import CompositionError

        assert isinstance(result, CompositionError)

    def test_validate_empty_name(self) -> None:
        wf = HexagramWorkflow(hexagram=1, role_name="")
        issues = RoleComposer.validate(wf)
        assert len(issues) > 0

    def test_validate_dead_zone(self) -> None:
        wf = HexagramWorkflow(hexagram=0, role_name="test")
        issues = RoleComposer.validate(wf)
        assert any("dead zone" in i for i in issues)

    def test_get_archetype(self) -> None:
        archetype = RoleComposer.get_archetype("坎")
        assert archetype is not None
        assert "风险导航" in archetype["name"]

    def test_get_archetype_nonexistent(self) -> None:
        assert RoleComposer.get_archetype("X") is None

    def test_dead_zone_avoided(self) -> None:
        core = PluginRole(
            maref_role="1.0",
            identity=PluginRoleIdentity(
                did="did:maref:core/neutral/v1", name="neutral", version="1.0"
            ),
            capability=PluginRoleCapability(trigram="坤", allowed_tools=["do"], max_entropy=10.0),
            trust=PluginRoleTrust(),
        )
        result = RoleComposer.compose(core, [])
        assert isinstance(result, HexagramWorkflow)
        assert result.hexagram not in DEAD_ZONE_HEXAGRAMS
