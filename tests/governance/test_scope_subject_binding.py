"""v0.47 S12 — agent_id binding + scope anti-forgery.

1. ``TrustBoundaryManager`` rejects a scope whose ``subject_did`` does not
   match the requesting ``agent_id`` — an agent can no longer present
   another agent's authorization scope.

2. ``AuthorizationScope`` gains an issuer Ed25519 signature; scopes can be
   verified against the issuer's public key (DIDRegistry-derived), so a
   forged scope with a bogus issuer fails verification.
"""

from __future__ import annotations

import pytest

from maref.governance.trust_boundary import TrustBoundaryManager
from maref.identity.credential import AuthorizationScope
from maref.signing.signing_key import ReportSigningKey


def _scope(subject_did: str, **kwargs: object) -> AuthorizationScope:
    fields: dict[str, object] = {
        "max_risk_level": "HIGH",
        "allowed_actions": ["file.delete"],
    }
    fields.update(kwargs)
    return AuthorizationScope(subject_did=subject_did, **fields)


class TestSubjectBinding:
    def test_scope_for_another_agent_rejected(self) -> None:
        """agent-B presenting agent-A's scope is denied."""
        scope = _scope("agent-A")
        boundary = TrustBoundaryManager(scope=scope)
        decision = boundary.check_no_raise("file.delete", agent_id="agent-B")
        assert decision.allowed is False
        assert "subject" in decision.reason or "agent" in decision.reason.lower()

    def test_scope_for_matching_agent_allowed(self) -> None:
        """agent-A's own scope works."""
        scope = _scope("agent-A")
        boundary = TrustBoundaryManager(scope=scope)
        decision = boundary.check_no_raise("file.delete", agent_id="agent-A")
        assert decision.allowed is True

    def test_boundary_check_raises_on_mismatch(self) -> None:
        """The raising `check()` path also rejects a mismatched subject."""
        scope = _scope("agent-A")
        boundary = TrustBoundaryManager(scope=scope)
        with pytest.raises(Exception, match="subject"):
            boundary.check("file.delete", agent_id="agent-C")


class TestScopeIssuerSignature:
    def test_scope_sign_and_verify_roundtrip(self) -> None:
        """A scope signed by its issuer verifies."""
        issuer = ReportSigningKey.generate()
        scope = _scope("agent-A", issuer="did:maref:issuer:alpha")
        scope.sign(issuer)
        assert scope.signature
        assert scope.verify_signature(issuer.public_key_pem) is True

    def test_forged_scope_rejected(self) -> None:
        """A scope signed by the wrong issuer fails verification."""
        real_issuer = ReportSigningKey.generate()
        attacker = ReportSigningKey.generate()
        scope = _scope("agent-A", issuer="did:maref:issuer:alpha")
        scope.sign(attacker)  # attacker signs, claims to be alpha
        assert scope.verify_signature(real_issuer.public_key_pem) is False

    def test_tampered_scope_rejected(self) -> None:
        """Changing scope fields invalidates the signature."""
        issuer = ReportSigningKey.generate()
        scope = _scope("agent-A", issuer="did:maref:issuer:alpha")
        scope.sign(issuer)
        scope.allowed_actions.append("payment:transfer")  # tamper
        assert scope.verify_signature(issuer.public_key_pem) is False

    def test_unsigned_scope_rejected(self) -> None:
        """An unsigned scope fails verification when verification is required."""
        scope = _scope("agent-A", issuer="did:maref:issuer:alpha")
        assert scope.verify_signature(ReportSigningKey.generate().public_key_pem) is False


class TestBoundaryVerifiesIssuer:
    def test_boundary_rejects_forged_issuer_scope(self) -> None:
        """TrustBoundaryManager rejects a scope whose issuer signature does
        not verify against the issuer's public key."""
        issuer = ReportSigningKey.generate()
        attacker = ReportSigningKey.generate()
        scope = _scope("agent-A", issuer="did:maref:issuer:alpha")
        scope.sign(attacker)  # forged
        boundary = TrustBoundaryManager(
            scope=scope,
            issuer_public_keys={"did:maref:issuer:alpha": issuer.public_key_pem},
        )
        decision = boundary.check_no_raise("file.delete", agent_id="agent-A")
        assert decision.allowed is False

    def test_boundary_accepts_valid_issuer_scope(self) -> None:
        """A scope properly signed by its issuer passes."""
        issuer = ReportSigningKey.generate()
        scope = _scope("agent-A", issuer="did:maref:issuer:alpha")
        scope.sign(issuer)
        boundary = TrustBoundaryManager(
            scope=scope,
            issuer_public_keys={"did:maref:issuer:alpha": issuer.public_key_pem},
        )
        decision = boundary.check_no_raise("file.delete", agent_id="agent-A")
        assert decision.allowed is True
