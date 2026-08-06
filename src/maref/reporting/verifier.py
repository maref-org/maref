from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from maref.governance.audit import AuditLogger
from maref.reporting.models import GovernanceReport


def _fingerprint_from_public_pem(pem: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )

    pub = serialization.load_pem_public_key(pem.encode("utf-8"))
    if not isinstance(pub, Ed25519PublicKey):
        return ""
    raw = pub.public_bytes_raw()
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass
class VerificationResult:
    passed: bool
    report_id: str
    checks: dict[str, bool] = field(default_factory=dict)
    details: list[str] = field(default_factory=list)

    def merge(self, check_name: str, ok: bool, detail: str = "") -> None:
        self.checks[check_name] = ok
        if detail:
            self.details.append(detail)
        if not ok:
            self.passed = False


class ReportVerifier:
    @staticmethod
    def verify_report(
        report: GovernanceReport,
        public_key_pem: str,
    ) -> VerificationResult:
        result = VerificationResult(passed=True, report_id=report.report_id)

        has_signature = bool(report.signature)
        result.merge("has_signature", has_signature, "signature field is empty" if not has_signature else "")

        valid_sig = report.verify_signature(public_key_pem)
        result.merge(
            "valid_signature",
            valid_sig,
            "signature does not match payload" if not valid_sig else "",
        )

        expected_fp = _fingerprint_from_public_pem(public_key_pem)
        fp_match = report.signer_fingerprint == expected_fp
        result.merge(
            "fingerprint_match",
            fp_match,
            f"expected {expected_fp}, got {report.signer_fingerprint}" if not fp_match else "",
        )

        consistent = True
        if report.audit_summary.total_events > 0 and not report.merkle_root:
            consistent = False
        result.merge(
            "merkle_root_consistent",
            consistent,
            "non-zero events but empty merkle_root" if not consistent else "",
        )

        return result

    @staticmethod
    def verify_report_with_audit_log(
        report: GovernanceReport,
        public_key_pem: str,
        audit_logger: AuditLogger,
    ) -> VerificationResult:
        result = ReportVerifier.verify_report(report, public_key_pem)

        entries = audit_logger.read_all(max_entries=None)
        if report.audit_summary.total_events != len(entries):
            result.merge(
                "event_count_matches",
                False,
                f"report says {report.audit_summary.total_events}, log has {len(entries)}",
            )
        else:
            result.merge("event_count_matches", True)

        if report.merkle_root:
            from maref.eivl.merkle_auditor import AuditChainIntegrator

            integrator = AuditChainIntegrator()
            for entry in entries:
                integrator.record_audit_entry(entry)
            actual_root = integrator.merkle.get_root_hash() or ""
            root_match = actual_root == report.merkle_root
            result.merge(
                "merkle_root_matches",
                root_match,
                f"expected {actual_root}, got {report.merkle_root}" if not root_match else "",
            )
        else:
            result.merge("merkle_root_matches", True)

        return result
