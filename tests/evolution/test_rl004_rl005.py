"""Tests for ConstitutionGuard RL-004 and RL-005 enforcement.

RL-004: Circuit breaker cannot be bypassed or disabled by policy updates.
RL-005: No privilege escalation through policy updates.
"""

from __future__ import annotations

from maref.evolution.constitution_guard import ConstitutionGuard


class TestRL004:
    def test_accepts_circuit_breaker_enabled(self):
        guard = ConstitutionGuard()
        violations = guard._check_circuit_breaker_invariant({"circuit_breaker_enabled": True})
        assert violations == []

    def test_rejects_circuit_breaker_disabled(self):
        guard = ConstitutionGuard()
        violations = guard._check_circuit_breaker_invariant({"circuit_breaker_enabled": False})
        assert len(violations) == 1
        assert "circuit breaker" in violations[0].lower()

    def test_rejects_cooldown_below_minimum(self):
        guard = ConstitutionGuard()
        violations = guard._check_circuit_breaker_invariant({"circuit_breaker_cooldown": 1.0})
        assert len(violations) == 1
        assert "cooldown" in violations[0].lower()

    def test_accepts_safe_cooldown(self):
        guard = ConstitutionGuard()
        violations = guard._check_circuit_breaker_invariant({"circuit_breaker_cooldown": 30.0})
        assert violations == []

    def test_no_violations_for_unrelated_weights(self):
        guard = ConstitutionGuard()
        violations = guard._check_circuit_breaker_invariant({"max_depth": 10})
        assert violations == []


class TestRL005:
    def test_accepts_no_privilege_key(self):
        guard = ConstitutionGuard()
        violations = guard._check_privilege_escalation({"max_depth": 10})
        assert violations == []

    def test_rejects_privilege_level_modification(self):
        guard = ConstitutionGuard()
        violations = guard._check_privilege_escalation({"max_privilege_level": 5})
        assert len(violations) == 1
        assert "privilege" in violations[0].lower()

    def test_accepts_empty_weights(self):
        guard = ConstitutionGuard()
        violations = guard._check_privilege_escalation({})
        assert violations == []

    def test_rejects_combined_violations(self):
        guard = ConstitutionGuard()
        violations = guard._check_privilege_escalation({
            "max_privilege_level": 3, "other": 1.0
        })
        assert len(violations) == 1
