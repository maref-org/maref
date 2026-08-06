"""
MAREF Constitution Guard — TLA+ Invariant Enforcement Layer

Enforces governance safety invariants derived from formal TLA+ specifications
on all policy update actions. Acts as a hard constraint layer preventing
optimization from violating core governance properties.

Invariants (derived from TLA+ formal models):
- RL-001: Only registered agents may modify policy weights
- RL-002: Safety thresholds cannot be set below minimum safe values
- RL-003: All policy changes must be auditable (trace preservation)
- RL-004: Circuit breaker cannot be disabled by policy updates
- RL-005: No privilege escalation through policy updates

These invariants correspond to the safety properties verified in:
- MarefLite.tla (Gray code state machine invariants)
- MAREF_Consensus.tla (Byzantine fault-tolerant consensus invariants)
- MarefLiteModel.tla (Executable governance model invariants)

The guard operates as a pre-commit hook: all proposed policy weights
must pass validation before being applied to the live system.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InvariantCode(str, Enum):
    """TLA+ invariant identifiers."""

    RL_001_MODIFIED_BY_REGISTERED = "rl_modified_by_not_in_agents"
    RL_002_SAFETY_GATE_ACTIVE = "safety_gate_always_active"
    RL_003_AUDIT_TRACE_REQUIRED = "audit_trace_required"
    RL_004_NO_BYPASS_CIRCUIT_BREAKER = "no_bypass_circuit_breaker"
    RL_005_NO_PRIVILEGE_ESCALATION = "no_privilege_escalation"
    RL_006_CROSS_DIM_SAFETY = "cross_dim_safety_violation"
    RL_007_MAX_FILES_PER_ROUND = "max_files_per_round_exceeded"
    RL_008_OUTPUT_SANITIZATION_REQUIRED = "output_sanitization_required"
    RL_009_DATA_LOCALIZATION = "data_localization_violation"
    RL_010_IDENTITY_VERIFICATION = "identity_verification_required"
    RL_011_SUPPLY_CHAIN_ATTESTATION = "supply_chain_attestation_required"
    RL_012_JURISDICTION_COMPLIANCE = "jurisdiction_compliance_violation"


# Safe bounds for policy weight features
SAFE_BOUNDS: dict[str, tuple[float, float]] = {
    "entropy_penalty": (-1.0, 1.0),
    "stability_bonus": (-1.0, 1.0),
    "transition_efficiency": (-1.0, 1.0),
    "kl_divergence_penalty": (-0.5, 0.5),
    "reward_scale": (0.1, 10.0),
    "learning_rate_scale": (0.01, 1.0),
}

# Features that must never be modified by agents
IMMUTABLE_FEATURES = frozenset(
    {
        "safety_gate_threshold",
        "circuit_breaker_enabled",
        "max_privilege_level",
        "audit_log_enabled",
        "cross_dim_safety_dimensions",
    }
)

# Minimum safe values for critical thresholds
MIN_SAFE_THRESHOLDS = {
    "kl_divergence_max": 0.1,
    "safety_gate_threshold": 0.5,
    "circuit_breaker_cooldown": 10.0,
}

# Maximum allowed values
MAX_THRESHOLDS = {
    "kl_divergence_max": 2.0,
    "safety_gate_threshold": 0.95,
    "circuit_breaker_cooldown": 300.0,
}


@dataclass
class ValidationResult:
    """Result of a constitution validation."""

    allowed: bool
    violations: list[str] = field(default_factory=list)
    invariant_codes: list[InvariantCode] = field(default_factory=list)
    constrained_weights: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "violations": self.violations,
            "invariant_codes": [c.value for c in self.invariant_codes],
        }


@dataclass
class InvariantViolation:
    """Record of a single invariant violation."""

    invariant: InvariantCode
    agent_id: str
    details: str
    timestamp: float = field(default_factory=time.time)
    proposed_weights: dict[str, float] = field(default_factory=dict)


class ConstitutionGuard:
    """
    Safety layer enforcing governance invariants on policy updates.

    This guard implements the runtime enforcement of TLA+ verified
    safety properties. It operates as a pre-commit validation layer:
    before any policy weight update is applied, it must pass all
    invariant checks.

    Invariants enforced:
    - RL-001: Modified-by invariant — only registered agents can propose
    - RL-002: Safety gate invariant — thresholds stay within safe bounds
    - RL-003: Audit trace invariant — all changes are logged
    - RL-004: Circuit breaker invariant — breaker cannot be bypassed
    - RL-005: Privilege invariant — no escalation through updates

    Usage:
        guard = ConstitutionGuard(enabled=True)
        guard.register_agent("detector_1")

        result = guard.validate_action("detector_1", {"entropy_penalty": 0.5})
        if result.allowed:
            apply_weights(result.constrained_weights)
    """

    # Global weight magnitude bound (prevents gradient explosion)
    MAX_WEIGHT_MAGNITUDE = 2.0

    # Security-related dimensions protected by RL-006
    SECURITY_DIMENSIONS = frozenset({"security", "safety_gate", "circuit_breaker"})

    # Maximum files per round enforced by RL-007
    MAX_FILES_PER_ROUND = 3

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._registered_agents: set[str] = set()
        self._violation_count = 0
        self._violation_log: list[InvariantViolation] = []

    # --- Public API ---

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def violation_count(self) -> int:
        return self._violation_count

    @property
    def violation_log(self) -> list[InvariantViolation]:
        return list(self._violation_log)

    def register_agent(self, agent_id: str) -> None:
        """Register an agent that is allowed to propose policy updates."""
        self._registered_agents.add(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        self._registered_agents.discard(agent_id)

    def validate_cross_dimension(
        self,
        agent_id: str,
        target_dimensions: list[str],
        target_files: list[str],
    ) -> ValidationResult:
        """Validate cross-dimension improvement action.

        Checks:
        - RL-006: No modification to security-related dimensions
          (security, safety_gate, circuit_breaker dimensions are protected)
        - RL-007: No more than 3 target files per round
        """
        if not self._enabled:
            return ValidationResult(allowed=True)

        violations: list[str] = []
        invariant_codes: list[InvariantCode] = []

        # RL-006: Cross-dim safety — block if any target dimension is protected
        protected_dims = self.SECURITY_DIMENSIONS & set(target_dimensions)
        if protected_dims:
            violations.append(
                f"Cross-dimension improvement targets protected dimensions: {sorted(protected_dims)}"
            )
            invariant_codes.append(InvariantCode.RL_006_CROSS_DIM_SAFETY)

        # RL-007: Max files per round
        if len(target_files) > self.MAX_FILES_PER_ROUND:
            violations.append(
                f"Cross-dimension improvement targets {len(target_files)} files, "
                f"exceeds maximum of {self.MAX_FILES_PER_ROUND}"
            )
            invariant_codes.append(InvariantCode.RL_007_MAX_FILES_PER_ROUND)

        if violations:
            self._violation_count += len(violations)
            for inv_code in invariant_codes:
                self._violation_log.append(
                    InvariantViolation(
                        invariant=inv_code,
                        agent_id=agent_id,
                        details="; ".join(violations),
                    )
                )
            return ValidationResult(
                allowed=False,
                violations=violations,
                invariant_codes=invariant_codes,
            )

        return ValidationResult(allowed=True)

    def validate_output(self, actor: str, output_text: str) -> ValidationResult:
        """
        Validate model output for Unicode steganography (RL-008).

        Args:
            actor: The agent producing the output.
            output_text: The model output text to check.

        Returns:
            ValidationResult. allowed=False if steganography markers detected.
        """
        if not self._enabled:
            return ValidationResult(allowed=True)

        from maref.security.steg_sanitizer import UnicodeAnomalyDetector

        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect(output_text)
        if anomalies:
            violations = [f"RL-008: output contains {len(anomalies)} Unicode anomalies"]
            invariant_codes = [InvariantCode.RL_008_OUTPUT_SANITIZATION_REQUIRED]
            self._violation_count += len(violations)
            for inv_code in invariant_codes:
                self._violation_log.append(
                    InvariantViolation(
                        invariant=inv_code,
                        agent_id=actor,
                        details=violations[0],
                    )
                )
            return ValidationResult(
                allowed=False,
                violations=violations,
                invariant_codes=invariant_codes,
            )
        return ValidationResult(allowed=True)

    def validate_deployment(
        self,
        actor: str,
        jurisdiction: str,
        data_residency: str,
    ) -> ValidationResult:
        """
        Validate deployment for data localization and jurisdiction compliance (RL-009, RL-012).

        Uses JURISDICTION_REGISTRY from governance.geopolitical_risk to check
        real jurisdiction codes (e.g., "RU", "IR", "KP" for sanctioned;
        "EU", "CN" for data sovereignty required).

        Args:
            actor: The agent requesting deployment.
            jurisdiction: Deployment jurisdiction code (e.g., "US", "EU", "CN", "RU").
            data_residency: Where data actually resides.

        Returns:
            ValidationResult with RL-009 and/or RL-012 violations if applicable.
        """
        if not self._enabled:
            return ValidationResult(allowed=True)

        from maref.governance.geopolitical_risk import JURISDICTION_REGISTRY

        violations: list[str] = []
        invariant_codes: list[InvariantCode] = []

        juris = JURISDICTION_REGISTRY.get(jurisdiction)

        # RL-012: Jurisdiction compliance — sanctioned jurisdictions blocked
        if juris is not None and juris.sanctions_active:
            violations.append(
                f"RL-012: jurisdiction {jurisdiction} is under sanctions"
            )
            invariant_codes.append(InvariantCode.RL_012_JURISDICTION_COMPLIANCE)

        # RL-009: Data localization — data sovereignty jurisdictions require local residency
        if juris is not None and juris.data_sovereignty_required and data_residency != jurisdiction:
            violations.append(
                "RL-009: data must reside in deployment jurisdiction "
                f"({jurisdiction}), got {data_residency}"
            )
            invariant_codes.append(InvariantCode.RL_009_DATA_LOCALIZATION)

        if violations:
            self._violation_count += len(violations)
            for inv_code in invariant_codes:
                self._violation_log.append(
                    InvariantViolation(
                        invariant=inv_code,
                        agent_id=actor,
                        details="; ".join(violations),
                    )
                )
            return ValidationResult(
                allowed=False,
                violations=violations,
                invariant_codes=invariant_codes,
            )
        return ValidationResult(allowed=True)

    def validate_identity(
        self,
        actor: str,
        identity_proven: bool,
    ) -> ValidationResult:
        """
        Validate agent identity verification (RL-010).

        Ensures that an agent's identity has been cryptographically verified
        before performing privileged operations.

        Args:
            actor: The agent requesting the privileged operation.
            identity_proven: Whether the agent's identity has been verified
                (e.g., via signature, attestation, or credential check).

        Returns:
            ValidationResult. allowed=False if identity not proven.
        """
        if not self._enabled:
            return ValidationResult(allowed=True)

        if not identity_proven:
            violations = [f"RL-010: agent '{actor}' identity not verified"]
            invariant_codes = [InvariantCode.RL_010_IDENTITY_VERIFICATION]
            self._violation_count += len(violations)
            for inv_code in invariant_codes:
                self._violation_log.append(
                    InvariantViolation(
                        invariant=inv_code,
                        agent_id=actor,
                        details=violations[0],
                    )
                )
            return ValidationResult(
                allowed=False,
                violations=violations,
                invariant_codes=invariant_codes,
            )
        return ValidationResult(allowed=True)

    def validate_supply_chain(self, actor: str, sbom: Any) -> ValidationResult:
        """
        Validate supply chain attestation (RL-011).

        Args:
            actor: The agent requesting supply chain verification.
            sbom: SBOM object to verify.

        Returns:
            ValidationResult. allowed=False if untrusted components found.
        """
        if not self._enabled:
            return ValidationResult(allowed=True)

        from maref.supply_chain.trust_verifier import SupplyChainVerifier

        verifier = SupplyChainVerifier()
        report = verifier.verify(sbom)
        if not report.attestation_valid:
            untrusted_sample = ", ".join(report.untrusted[:5])
            violations = [
                f"RL-011: {len(report.untrusted)} untrusted components: {untrusted_sample}"
            ]
            invariant_codes = [InvariantCode.RL_011_SUPPLY_CHAIN_ATTESTATION]
            self._violation_count += len(violations)
            for inv_code in invariant_codes:
                self._violation_log.append(
                    InvariantViolation(
                        invariant=inv_code,
                        agent_id=actor,
                        details=violations[0],
                    )
                )
            return ValidationResult(
                allowed=False,
                violations=violations,
                invariant_codes=invariant_codes,
            )
        return ValidationResult(allowed=True)

    def reset(self) -> None:
        """Reset violation counters and logs."""
        self._violation_count = 0
        self._violation_log.clear()

    def validate_action(
        self,
        agent_id: str,
        proposed_weights: dict[str, float],
    ) -> ValidationResult:
        """
        Validate proposed policy weights against all invariants.

        Args:
            agent_id: The agent proposing the update.
            proposed_weights: Dictionary of feature → weight values.

        Returns:
            ValidationResult with allowed flag and violation details.
            If allowed=False, the weights should NOT be applied.
            If allowed=True, constrained_weights may contain clipped values.
        """
        if not self._enabled:
            return ValidationResult(allowed=True, constrained_weights=proposed_weights)

        violations: list[str] = []
        invariant_codes: list[InvariantCode] = []

        # RL-001: Modified-by invariant
        if agent_id not in self._registered_agents:
            violations.append(f"Agent '{agent_id}' is not registered to modify policy weights")
            invariant_codes.append(InvariantCode.RL_001_MODIFIED_BY_REGISTERED)

        # RL-002: Safety gate invariant
        safety_violations = self._check_safety_bounds(proposed_weights)
        if safety_violations:
            violations.extend(safety_violations)
            invariant_codes.append(InvariantCode.RL_002_SAFETY_GATE_ACTIVE)

        # RL-003: Audit trace invariant
        audit_violations = self._check_audit_requirements(proposed_weights)
        if audit_violations:
            violations.extend(audit_violations)
            invariant_codes.append(InvariantCode.RL_003_AUDIT_TRACE_REQUIRED)

        # RL-004: Circuit breaker invariant
        breaker_violations = self._check_circuit_breaker_invariant(proposed_weights)
        if breaker_violations:
            violations.extend(breaker_violations)
            invariant_codes.append(InvariantCode.RL_004_NO_BYPASS_CIRCUIT_BREAKER)

        # RL-005: Privilege escalation invariant
        privilege_violations = self._check_privilege_escalation(proposed_weights)
        if privilege_violations:
            violations.extend(privilege_violations)
            invariant_codes.append(InvariantCode.RL_005_NO_PRIVILEGE_ESCALATION)

        if not violations:
            # All invariants satisfied — apply safe clipping
            constrained = self._constrain_weights(proposed_weights)
            return ValidationResult(
                allowed=True,
                constrained_weights=constrained,
            )

        # Record violations
        self._violation_count += len(violations)
        for inv_code in invariant_codes:
            self._violation_log.append(
                InvariantViolation(
                    invariant=inv_code,
                    agent_id=agent_id,
                    details="; ".join(violations),
                    proposed_weights=proposed_weights,
                )
            )

        return ValidationResult(
            allowed=False,
            violations=violations,
            invariant_codes=invariant_codes,
        )

    def constrain_weights(
        self,
        weights: dict[str, float],
    ) -> dict[str, float]:
        """
        Clip weights to safe bounds without raising violations.

        This is a soft constraint applied after validation passes,
        ensuring numerical stability even for valid updates.
        """
        if not self._enabled:
            return dict(weights)

        return self._constrain_weights(weights)

    def get_stats(self) -> dict[str, Any]:
        """Get guard statistics."""
        return {
            "enabled": self._enabled,
            "registered_agents": len(self._registered_agents),
            "violation_count": self._violation_count,
            "recent_violations": [
                {
                    "invariant": v.invariant.value,
                    "agent_id": v.agent_id,
                    "details": v.details,
                }
                for v in self._violation_log[-10:]
            ],
        }

    # --- Private invariant checks ---

    def _check_safety_bounds(
        self,
        weights: dict[str, float],
    ) -> list[str]:
        """RL-002: Ensure all weights stay within safe numerical bounds."""
        violations: list[str] = []

        # Features exempt from global magnitude check (have their own bounds)
        exempt_from_global_check = (
            frozenset(SAFE_BOUNDS.keys())
            | frozenset(MIN_SAFE_THRESHOLDS.keys())
            | frozenset(MAX_THRESHOLDS.keys())
        )

        for feature, value in weights.items():
            if feature in IMMUTABLE_FEATURES:
                # Only reject if trying to set to unsafe value
                if feature in ("circuit_breaker_enabled", "audit_log_enabled"):
                    if not value:
                        violations.append(f"Immutable feature '{feature}' cannot be disabled")
                else:
                    violations.append(f"Immutable feature '{feature}' cannot be modified")
                continue

            bounds = SAFE_BOUNDS.get(feature)
            if bounds is not None:
                low, high = bounds
                if value < low or value > high:
                    violations.append(
                        f"Feature '{feature}' value {value} outside safe bounds [{low}, {high}]"
                    )
            # Global magnitude check (skip for features with their own bounds)
            elif feature not in exempt_from_global_check:
                if abs(value) > self.MAX_WEIGHT_MAGNITUDE:
                    violations.append(
                        f"Feature '{feature}' magnitude {abs(value)} exceeds maximum {self.MAX_WEIGHT_MAGNITUDE}"
                    )

        # Check threshold features
        for feature, value in weights.items():
            if feature in MIN_SAFE_THRESHOLDS:
                if value < MIN_SAFE_THRESHOLDS[feature]:
                    violations.append(
                        f"Threshold '{feature}' value {value} below minimum safe value {MIN_SAFE_THRESHOLDS[feature]}"
                    )
            if feature in MAX_THRESHOLDS:
                if value > MAX_THRESHOLDS[feature]:
                    violations.append(
                        f"Threshold '{feature}' value {value} exceeds maximum {MAX_THRESHOLDS[feature]}"
                    )

        return violations

    def _check_audit_requirements(
        self,
        weights: dict[str, float],
    ) -> list[str]:
        """RL-003: Ensure policy changes don't disable audit logging."""
        violations: list[str] = []

        if "audit_log_enabled" in weights and not weights["audit_log_enabled"]:
            violations.append("Policy update attempts to disable audit logging")

        return violations

    def _check_circuit_breaker_invariant(
        self,
        weights: dict[str, float],
    ) -> list[str]:
        """RL-004: Ensure circuit breaker cannot be bypassed or disabled."""
        violations: list[str] = []

        if "circuit_breaker_enabled" in weights and not weights["circuit_breaker_enabled"]:
            violations.append("Policy update attempts to disable circuit breaker")

        if "circuit_breaker_cooldown" in weights:
            cooldown = weights["circuit_breaker_cooldown"]
            if cooldown < MIN_SAFE_THRESHOLDS.get("circuit_breaker_cooldown", 10.0):
                violations.append(f"Circuit breaker cooldown {cooldown}s below minimum safe value")

        return violations

    def _check_privilege_escalation(
        self,
        weights: dict[str, float],
    ) -> list[str]:
        """RL-005: Ensure no privilege escalation through policy updates."""
        violations: list[str] = []

        if "max_privilege_level" in weights:
            violations.append(
                "Policy update attempts to modify privilege level — escalation not allowed"
            )

        return violations

    @staticmethod
    def _constrain_weights(weights: dict[str, float]) -> dict[str, float]:
        """Clip weights to safe bounds."""
        constrained: dict[str, float] = {}

        for feature, value in weights.items():
            if feature in IMMUTABLE_FEATURES:
                constrained[feature] = value
                continue

            bounds = SAFE_BOUNDS.get(feature)
            if bounds is not None:
                low, high = bounds
                constrained[feature] = max(low, min(high, value))
            else:
                # Apply global magnitude bound
                constrained[feature] = max(
                    -ConstitutionGuard.MAX_WEIGHT_MAGNITUDE,
                    min(ConstitutionGuard.MAX_WEIGHT_MAGNITUDE, value),
                )

        return constrained
