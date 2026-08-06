"""Tests for ConstitutionGuard — TLA+ invariant enforcement layer."""

from __future__ import annotations

import pytest

from maref.evolution.constitution_guard import (
    ConstitutionGuard,
    InvariantCode,
    InvariantViolation,
    ValidationResult,
)


class TestConstitutionGuardBasic:
    """Basic guard functionality tests."""

    def test_enabled_by_default(self) -> None:
        guard = ConstitutionGuard()
        assert guard.enabled is True

    def test_can_disable(self) -> None:
        guard = ConstitutionGuard(enabled=False)
        assert guard.enabled is False

    def test_violation_count_starts_at_zero(self) -> None:
        guard = ConstitutionGuard()
        assert guard.violation_count == 0

    def test_violation_log_starts_empty(self) -> None:
        guard = ConstitutionGuard()
        assert guard.violation_log == []

    def test_reset_clears_violations(self) -> None:
        guard = ConstitutionGuard()
        guard._violation_count = 5
        guard._violation_log.append(
            InvariantViolation(
                invariant=InvariantCode.RL_001_MODIFIED_BY_REGISTERED,
                agent_id="test",
                details="test",
            )
        )
        guard.reset()
        assert guard.violation_count == 0
        assert guard.violation_log == []


class TestAgentRegistration:
    """Agent registration/unregistration tests."""

    def test_register_agent(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"entropy_penalty": 0.5})
        assert result.allowed is True

    def test_unregister_agent(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        guard.unregister_agent("agent_1")
        result = guard.validate_action("agent_1", {"entropy_penalty": 0.5})
        assert result.allowed is False

    def test_unregistered_agent_rejected(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_action("unknown_agent", {"entropy_penalty": 0.5})
        assert result.allowed is False
        assert len(result.violations) == 1
        assert InvariantCode.RL_001_MODIFIED_BY_REGISTERED in result.invariant_codes

    def test_multiple_agents(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        guard.register_agent("agent_2")
        guard.register_agent("agent_3")

        for agent_id in ["agent_1", "agent_2", "agent_3"]:
            result = guard.validate_action(agent_id, {"entropy_penalty": 0.3})
            assert result.allowed is True


class TestRl001ModifiedByRegistered:
    """RL-001: Only registered agents may modify policy weights."""

    def test_registered_agent_allowed(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("detector_1")
        result = guard.validate_action("detector_1", {"entropy_penalty": 0.5})
        assert result.allowed is True

    def test_unregistered_agent_rejected(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_action("hacker", {"entropy_penalty": 0.5})
        assert result.allowed is False
        assert any("not registered" in v for v in result.violations)

    def test_violation_logged(self) -> None:
        guard = ConstitutionGuard()
        guard.validate_action("hacker", {"entropy_penalty": 0.5})
        assert guard.violation_count >= 1
        assert len(guard.violation_log) >= 1
        assert guard.violation_log[0].agent_id == "hacker"


class TestRl002SafetyGateActive:
    """RL-002: Safety thresholds cannot be set below minimum safe values."""

    def test_weight_within_bounds(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"entropy_penalty": 0.5})
        assert result.allowed is True

    def test_weight_exceeds_upper_bound(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"entropy_penalty": 1.5})
        assert result.allowed is False
        assert any("outside safe bounds" in v for v in result.violations)

    def test_weight_below_lower_bound(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"entropy_penalty": -1.5})
        assert result.allowed is False
        assert any("outside safe bounds" in v for v in result.violations)

    def test_global_magnitude_exceeded(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"unknown_feature": 3.0})
        assert result.allowed is False
        assert any("magnitude" in v for v in result.violations)

    def test_immutable_feature_rejected(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"safety_gate_threshold": 0.3})
        assert result.allowed is False
        assert any("Immutable feature" in v for v in result.violations)

    def test_kl_divergence_within_bounds(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"kl_divergence_penalty": 0.3})
        assert result.allowed is True

    def test_kl_divergence_exceeded(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"kl_divergence_penalty": 0.6})
        assert result.allowed is False

    def test_reward_scale_within_bounds(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"reward_scale": 5.0})
        assert result.allowed is True

    def test_reward_scale_out_of_bounds(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"reward_scale": 0.01})
        assert result.allowed is False

    def test_multiple_violations(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action(
            "agent_1",
            {
                "entropy_penalty": 2.0,
                "kl_divergence_penalty": 0.8,
            },
        )
        assert result.allowed is False
        assert len(result.violations) >= 2


class TestRl003AuditTraceRequired:
    """RL-003: All policy changes must be auditable."""

    def test_audit_enabled_allowed(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"audit_log_enabled": True})
        assert result.allowed is True

    def test_audit_disabled_rejected(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"audit_log_enabled": False})
        assert result.allowed is False
        assert any("disable audit logging" in v for v in result.violations)


class TestRl004NoBypassCircuitBreaker:
    """RL-004: Circuit breaker cannot be disabled by policy updates."""

    def test_circuit_breaker_enabled_allowed(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"circuit_breaker_enabled": True})
        assert result.allowed is True

    def test_circuit_breaker_disabled_rejected(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"circuit_breaker_enabled": False})
        assert result.allowed is False
        assert any("disable circuit breaker" in v for v in result.violations)

    def test_cooldown_too_low_rejected(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"circuit_breaker_cooldown": 1.0})
        assert result.allowed is False
        assert any("cooldown" in v for v in result.violations)

    def test_cooldown_acceptable(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"circuit_breaker_cooldown": 30.0})
        assert result.allowed is True


class TestRl005NoPrivilegeEscalation:
    """RL-005: No privilege escalation through policy updates."""

    def test_privilege_level_modification_rejected(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"max_privilege_level": 10})
        assert result.allowed is False
        assert any("privilege" in v.lower() for v in result.violations)


class TestConstrainWeights:
    """Weight constraint/clipping tests."""

    def test_constrain_within_bounds(self) -> None:
        guard = ConstitutionGuard()
        weights = {"entropy_penalty": 0.5}
        constrained = guard.constrain_weights(weights)
        assert constrained["entropy_penalty"] == 0.5

    def test_constrain_clips_upper(self) -> None:
        guard = ConstitutionGuard()
        weights = {"entropy_penalty": 2.0}
        constrained = guard.constrain_weights(weights)
        assert constrained["entropy_penalty"] == 1.0

    def test_constrain_clips_lower(self) -> None:
        guard = ConstitutionGuard()
        weights = {"entropy_penalty": -2.0}
        constrained = guard.constrain_weights(weights)
        assert constrained["entropy_penalty"] == -1.0

    def test_constrain_unknown_feature_global_bound(self) -> None:
        guard = ConstitutionGuard()
        weights = {"custom_feature": 5.0}
        constrained = guard.constrain_weights(weights)
        assert constrained["custom_feature"] == 2.0

    def test_constrain_does_not_modify_when_disabled(self) -> None:
        guard = ConstitutionGuard(enabled=False)
        weights = {"entropy_penalty": 5.0}
        constrained = guard.constrain_weights(weights)
        assert constrained["entropy_penalty"] == 5.0

    def test_constrain_immutable_feature_preserved(self) -> None:
        guard = ConstitutionGuard()
        weights = {"safety_gate_threshold": 0.9}
        constrained = guard.constrain_weights(weights)
        assert constrained["safety_gate_threshold"] == 0.9


class TestValidationResult:
    """ValidationResult dataclass tests."""

    def test_to_dict(self) -> None:
        result = ValidationResult(
            allowed=True,
            constrained_weights={"entropy_penalty": 0.5},
        )
        d = result.to_dict()
        assert d["allowed"] is True
        assert d["violations"] == []
        assert d["invariant_codes"] == []

    def test_to_dict_with_violations(self) -> None:
        result = ValidationResult(
            allowed=False,
            violations=["test violation"],
            invariant_codes=[InvariantCode.RL_001_MODIFIED_BY_REGISTERED],
        )
        d = result.to_dict()
        assert d["allowed"] is False
        assert d["violations"] == ["test violation"]
        assert d["invariant_codes"] == ["rl_modified_by_not_in_agents"]


class TestGuardStats:
    """Guard statistics tests."""

    def test_get_stats(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        guard.register_agent("agent_2")
        stats = guard.get_stats()
        assert stats["enabled"] is True
        assert stats["registered_agents"] == 2
        assert stats["violation_count"] == 0

    def test_get_stats_after_violations(self) -> None:
        guard = ConstitutionGuard()
        guard.validate_action("hacker", {"entropy_penalty": 0.5})
        stats = guard.get_stats()
        assert stats["violation_count"] >= 1
        assert len(stats["recent_violations"]) >= 1

    def test_get_stats_recent_violations_limited(self) -> None:
        guard = ConstitutionGuard()
        for i in range(20):
            guard.validate_action(f"hacker_{i}", {"entropy_penalty": 0.5})
        stats = guard.get_stats()
        assert len(stats["recent_violations"]) <= 10


class TestDisabledGuard:
    """Tests for guard disabled mode."""

    def test_all_actions_allowed_when_disabled(self) -> None:
        guard = ConstitutionGuard(enabled=False)
        result = guard.validate_action(
            "anyone",
            {
                "entropy_penalty": 100.0,
                "circuit_breaker_enabled": False,
                "audit_log_enabled": False,
                "max_privilege_level": 999,
            },
        )
        assert result.allowed is True

    def test_constrain_returns_original_when_disabled(self) -> None:
        guard = ConstitutionGuard(enabled=False)
        weights = {"entropy_penalty": 100.0}
        constrained = guard.constrain_weights(weights)
        assert constrained == weights


class TestInvariantViolationRecord:
    """InvariantViolation dataclass tests."""

    def test_violation_record(self) -> None:
        violation = InvariantViolation(
            invariant=InvariantCode.RL_002_SAFETY_GATE_ACTIVE,
            agent_id="agent_1",
            details="weight out of bounds",
            proposed_weights={"entropy_penalty": 5.0},
        )
        assert violation.invariant == InvariantCode.RL_002_SAFETY_GATE_ACTIVE
        assert violation.agent_id == "agent_1"
        assert "weight out of bounds" in violation.details
        assert violation.proposed_weights["entropy_penalty"] == 5.0
        assert violation.timestamp > 0


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_empty_weights(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {})
        assert result.allowed is True

    def test_boundary_values_accepted(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"entropy_penalty": 1.0})
        assert result.allowed is True

        result = guard.validate_action("agent_1", {"entropy_penalty": -1.0})
        assert result.allowed is True

    def test_zero_weights(self) -> None:
        guard = ConstitutionGuard()
        guard.register_agent("agent_1")
        result = guard.validate_action("agent_1", {"entropy_penalty": 0.0})
        assert result.allowed is True

    def test_all_invariants_violated_simultaneously(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_action(
            "unknown",
            {
                "entropy_penalty": 5.0,
                "audit_log_enabled": False,
                "circuit_breaker_enabled": False,
                "max_privilege_level": 10,
            },
        )
        assert result.allowed is False
        assert len(result.invariant_codes) >= 4

    def test_violation_log_not_mutated_by_external_code(self) -> None:
        guard = ConstitutionGuard()
        guard.validate_action("hacker", {"entropy_penalty": 0.5})
        log = guard.violation_log
        log.clear()  # Should not affect internal log
        assert len(guard.violation_log) >= 1


class TestRl006CrossDimSafety:
    """RL-006: Cross-dimension improvements must not modify safety-related dimensions."""

    def test_security_dimension_blocked(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["security", "performance"],
            target_files=["file1.py"],
        )
        assert result.allowed is False
        assert InvariantCode.RL_006_CROSS_DIM_SAFETY in result.invariant_codes
        assert any("protected dimensions" in v for v in result.violations)

    def test_non_safety_dimension_allowed(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["performance", "memory", "latency"],
            target_files=["file1.py"],
        )
        assert result.allowed is True
        assert result.violations == []

    def test_partial_safety_dimensions_blocked(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["security", "latency"],
            target_files=["file1.py"],
        )
        assert result.allowed is False
        assert InvariantCode.RL_006_CROSS_DIM_SAFETY in result.invariant_codes

    def test_empty_dimensions_allowed(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=[],
            target_files=["file1.py"],
        )
        assert result.allowed is True


class TestRl007MaxFilesPerRound:
    """RL-007: No more than 3 target files per round."""

    def test_three_files_allowed_boundary(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["performance"],
            target_files=["f1.py", "f2.py", "f3.py"],
        )
        assert result.allowed is True

    def test_four_files_blocked(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["performance"],
            target_files=["f1.py", "f2.py", "f3.py", "f4.py"],
        )
        assert result.allowed is False
        assert InvariantCode.RL_007_MAX_FILES_PER_ROUND in result.invariant_codes
        assert any("exceeds maximum" in v for v in result.violations)

    def test_empty_files_allowed(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["performance"],
            target_files=[],
        )
        assert result.allowed is True


class TestRl006Rl007Combined:
    """Combined RL-006 and RL-007 violations."""

    def test_both_violations_detected(self) -> None:
        guard = ConstitutionGuard()
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["security", "performance"],
            target_files=["f1.py", "f2.py", "f3.py", "f4.py"],
        )
        assert result.allowed is False
        assert InvariantCode.RL_006_CROSS_DIM_SAFETY in result.invariant_codes
        assert InvariantCode.RL_007_MAX_FILES_PER_ROUND in result.invariant_codes
        assert len(result.violations) == 2

    def test_disabled_guard_allows_all(self) -> None:
        guard = ConstitutionGuard(enabled=False)
        result = guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["security", "safety_gate"],
            target_files=["f1.py", "f2.py", "f3.py", "f4.py", "f5.py"],
        )
        assert result.allowed is True

    def test_violation_logged_properly(self) -> None:
        guard = ConstitutionGuard()
        guard.validate_cross_dimension(
            "agent_1",
            target_dimensions=["circuit_breaker"],
            target_files=["f1.py", "f2.py", "f3.py", "f4.py"],
        )
        assert guard.violation_count == 2
        assert len(guard.violation_log) == 2
        codes = [v.invariant for v in guard.violation_log]
        assert InvariantCode.RL_006_CROSS_DIM_SAFETY in codes
        assert InvariantCode.RL_007_MAX_FILES_PER_ROUND in codes
