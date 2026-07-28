"""Ed25519 key pair management for Agent Card cryptographic signing.

Provides Ed25519 key generation, PEM serialization, signing, and verification
using the ``cryptography`` library. Replaces the previous SHA-256 simulation
(``ed25519-sim``) with real elliptic curve digital signatures.

Ed25519 is used for Agent Card signing in the federation layer because:
- Non-interactive: signing does not require a round-trip to a KMS.
- Deterministic: same key + message always produces the same signature.
- Compact: 64-byte signatures, 32-byte keys.
- Cross-organization verifiable: public keys can be freely shared.

Dependency: cryptography>=42.0 (in ``[identity]`` optional-dependencies).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


def _load_cryptography() -> tuple[Any, Any, Any, Any]:
    """Lazy-import cryptography to avoid hard dependency at import time.

    Returns:
        A tuple of (Ed25519PrivateKey, Ed25519PublicKey, serialization, InvalidSignature).
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

    return Ed25519PrivateKey, Ed25519PublicKey, serialization, InvalidSignature


@dataclass
class Ed25519KeyPair:
    """An Ed25519 key pair for Agent Card signing and verification.

    Attributes:
        private_key_pem: PEM-encoded PKCS#8 private key.
        public_key_pem: PEM-encoded SubjectPublicKeyInfo public key.
    """

    private_key_pem: str
    public_key_pem: str
    _cached_private_key: Any = None
    _cached_public_key: Any = None

    @classmethod
    def generate(cls) -> Ed25519KeyPair:
        """Generate a new Ed25519 key pair.

        Returns:
            A new :class:`Ed25519KeyPair` with fresh keys.
        """
        Ed25519PrivateKey, _, serialization, _ = _load_cryptography()

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        return cls(private_key_pem=private_pem, public_key_pem=public_pem)

    @classmethod
    def from_private_pem(cls, private_key_pem: str) -> Ed25519KeyPair:
        """Load a key pair from a PEM-encoded private key.

        Args:
            private_key_pem: PEM-encoded Ed25519 private key.

        Returns:
            A :class:`Ed25519KeyPair` with the corresponding public key.

        Raises:
            ValueError: If the PEM is not a valid Ed25519 private key.
        """
        Ed25519PrivateKey, _, serialization, _ = _load_cryptography()

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
        )
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("Not an Ed25519 private key")

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        return cls(private_key_pem=private_key_pem, public_key_pem=public_pem)

    def _get_private_key(self) -> Any:
        """Lazy-load and cache the Ed25519 private key from PEM."""
        if self._cached_private_key is not None:
            return self._cached_private_key
        (
            Ed25519PrivateKey,
            _,
            serialization,
            _,
        ) = _load_cryptography()
        private_key = serialization.load_pem_private_key(
            self.private_key_pem.encode("utf-8"),
            password=None,
        )
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("Not an Ed25519 private key")
        self._cached_private_key = private_key
        return private_key

    def sign(self, message: bytes) -> bytes:
        """Sign a message with the private key.

        Args:
            message: The bytes to sign.

        Returns:
            The 64-byte Ed25519 signature.

        Raises:
            ValueError: If the private key PEM is not a valid Ed25519 key.
        """
        private_key = self._get_private_key()
        return private_key.sign(message)

    @staticmethod
    def verify(public_key_pem: str, signature: bytes, message: bytes) -> bool:
        """Verify a signature against a message using a public key.

        Args:
            public_key_pem: PEM-encoded Ed25519 public key.
            signature: The 64-byte signature to verify.
            message: The original signed bytes.

        Returns:
            True if the signature is valid, False otherwise.
            Never raises on invalid signatures -- returns False.
        """
        _, Ed25519PublicKey, serialization, InvalidSignature = _load_cryptography()

        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode("utf-8"),
            )
            if not isinstance(public_key, Ed25519PublicKey):
                return False
            public_key.verify(signature, message)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    @property
    def fingerprint(self) -> str:
        """A 16-char hex fingerprint of the public key.

        Used as a compact identifier in :class:`AgentCardSignature`.
        """
        return hashlib.sha256(self.public_key_pem.encode("utf-8")).hexdigest()[:16]


__all__ = ["Ed25519KeyPair"]
