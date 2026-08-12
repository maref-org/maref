"""P5.1: MetaRatchet recursive hardening.

Provides an independent audit layer that prevents recursive evolution from
bypassing or downgrading the ratchet mechanism:

- Blocks changes to CONSTITUTIONAL_IMMUTABLES / CONFIGURATIONAL_IMMUTABLES
- Blocks threshold relaxation in TRIGGER_CONDITIONS
- Blocks recursive-evolution modifications to ratchet source files
- Audits baseline score regression (the "only-forward" guarantee)

While MetaRatchet._check_self_modification guards against changes via
propose_protocol_change(), MetaRatchetAuditor guards against recursive-
evolution direct file modifications and threshold downgrades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maref.integration.percv.meta_ratchet import MetaRatchet


@dataclass
class AuditVerdict:
    """Outcome of a MetaRatchet audit check."""

    blocked: bool = False
    warning: bool = False
    reason: str = ""


# Ratchet source files protected from recursive-evolution direct modification.
RATCHET_SOURCE_FILES: frozenset[str] = frozenset(
    {
        "meta_ratchet.py",
        "ratchet_bridge.py",
        "meta_ratchet_auditor.py",
        "multi_target_ratchet.py",
    }
)


class MetaRatchetAuditor:
    """P5.1: Audits ratchet configuration and source-file changes.

    Complements MetaRatchet's internal self-modification protection with an
    independent audit layer that guards against recursive-evolution direct
    file modifications and threshold downgrades.
    """

    def __init__(self) -> None:
        self._audit_log: list[dict[str, Any]] = []

    def audit_config_change(
        self,
        target_key: str,
        old_value: Any,
        new_value: Any,
        source: str = "recursive_evolution",
    ) -> AuditVerdict:
        """Audit a proposed ratchet configuration change.

        Returns AuditVerdict with blocked=True if the change must be rejected.
        """
        # 1. Constitutional immutables - always blocked
        if target_key in MetaRatchet.CONSTITUTIONAL_IMMUTABLES:
            verdict = AuditVerdict(
                blocked=True,
                reason=f"constitutional immutable '{target_key}' cannot be modified",
            )
            self._log("config", target_key, verdict, source)
            return verdict

        # 2. Configurational immutables - always blocked
        if target_key in MetaRatchet.CONFIGURATIONAL_IMMUTABLES:
            verdict = AuditVerdict(
                blocked=True,
                reason=f"configurational immutable '{target_key}' cannot be modified",
            )
            self._log("config", target_key, verdict, source)
            return verdict

        # 3. TRIGGER_CONDITIONS threshold relaxation - blocked
        if target_key.startswith("TRIGGER_CONDITIONS"):
            if self._is_threshold_relaxed(old_value, new_value):
                verdict = AuditVerdict(
                    blocked=True,
                    reason=(
                        f"trigger threshold relaxed for '{target_key}': {old_value} -> {new_value}"
                    ),
                )
                self._log("config", target_key, verdict, source)
                return verdict

        # 4. Non-meta-ratchet source - warning
        if source != "meta_ratchet":
            verdict = AuditVerdict(
                warning=True,
                reason=f"non-meta-ratchet source '{source}' modifying '{target_key}'",
            )
            self._log("config", target_key, verdict, source)
            return verdict

        verdict = AuditVerdict(blocked=False, warning=False, reason="allowed")
        self._log("config", target_key, verdict, source)
        return verdict

    def audit_file_change(
        self,
        file_path: str,
        source: str = "recursive_evolution",
    ) -> AuditVerdict:
        """Audit a proposed ratchet source-file change.

        Recursive evolution is blocked from directly modifying ratchet
        source files; only manual (human) changes are allowed with warning.
        """
        for protected in RATCHET_SOURCE_FILES:
            if protected in file_path:
                if source == "recursive_evolution":
                    verdict = AuditVerdict(
                        blocked=True,
                        reason=(
                            f"ratchet source file '{protected}' protected from recursive evolution"
                        ),
                    )
                else:
                    verdict = AuditVerdict(
                        warning=True,
                        reason=f"manual modification of ratchet file '{protected}'",
                    )
                self._log("file", file_path, verdict, source)
                return verdict

        return AuditVerdict(blocked=False, warning=False, reason="not a ratchet file")

    def audit_baseline(
        self,
        old_baseline: float,
        new_baseline: float,
        source: str = "recursive_evolution",
    ) -> AuditVerdict:
        """Audit a ratchet baseline score change - blocks regression."""
        if new_baseline < old_baseline:
            verdict = AuditVerdict(
                blocked=True,
                reason=f"baseline regression: {old_baseline} -> {new_baseline}",
            )
            self._log("baseline", "best_score", verdict, source)
            return verdict
        verdict = AuditVerdict(blocked=False, reason="baseline maintained or improved")
        self._log("baseline", "best_score", verdict, source)
        return verdict

    def _is_threshold_relaxed(self, old_value: Any, new_value: Any) -> bool:
        """Check if a threshold change relaxes the ratchet constraint."""
        if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
            return new_value > old_value
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            old_t = old_value.get("threshold", 0)
            new_t = new_value.get("threshold", 0)
            old_cd = old_value.get("cooldown_rounds", 0)
            new_cd = new_value.get("cooldown_rounds", 0)
            old_mff = old_value.get("max_flip_flops", 0)
            new_mff = new_value.get("max_flip_flops", 0)
            old_it = old_value.get("improvement_threshold", 0)
            new_it = new_value.get("improvement_threshold", 0)
            # threshold increase, cooldown decrease, max_flip_flops increase,
            # or improvement_threshold increase all relax the ratchet
            if new_t > old_t or new_cd < old_cd or new_mff > old_mff or new_it > old_it:
                return True
        return False

    def _log(
        self,
        change_type: str,
        target: str,
        verdict: AuditVerdict,
        source: str,
    ) -> None:
        self._audit_log.append(
            {
                "type": change_type,
                "target": target,
                "blocked": verdict.blocked,
                "warning": verdict.warning,
                "reason": verdict.reason,
                "source": source,
            }
        )

    @property
    def audit_count(self) -> int:
        return len(self._audit_log)

    @property
    def blocked_count(self) -> int:
        return sum(1 for e in self._audit_log if e["blocked"])

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)
