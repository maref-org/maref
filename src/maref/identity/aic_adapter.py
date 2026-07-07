"""AIC (Agent Identity Code) Adapter.

Implements the ACPs AIC specification: hierarchical OID-based identifier
with AUTOSAR CRC-16/CCITT-FALSE checksum and Base36 encoding.

Provides bidirectional mapping between MAREF's W3C DID identifiers
(``did:maref:{namespace}:{short_id}``) and ACPs AIC identifiers
(``1.2.156.3088.{ARSP}.{Provider}.{Onto}.{Entity}.{Version}.{Checksum}``).

Reference: AIP-ACPs-Technical-Analysis.md section 2.1 (AIC v2.00).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

from maref.identity.did_registry import AgentDID

# AIP OID root: ISO → country member → China → AIP-specific OID node.
AIC_OID_ROOT = "1.2.156.3088"

# Default ARSP (Agent Registration Service Provider) identifier.
DEFAULT_ARSP = "1"

# Entity sequence length in Base36 (per AIC spec, up to 36^9 entities per ontology).
_ENTITY_SEQ_LENGTH = 9

# Pattern for a valid AIC string.
_AIC_PATTERN = re.compile(
    r"^"
    rf"{re.escape(AIC_OID_ROOT)}"
    r"(?:\.(\d+))"  # ARSP
    r"(?:\.(\d+))"  # ProviderID
    r"(?:\.(\d+))"  # OntologySeq
    r"(?:\.([0-9A-Za-z]+))"  # EntitySeq (Base36)
    r"(?:\.(\d+))"  # Version
    r"(?:\.([0-9A-Za-z]+))"  # Checksum (Base36)
    r"$"
)

# AIC checksums follow the spec (CRC-16/CCITT-FALSE over the OID payload)
# and are NOT salted. There is no per-deployment salt to configure.


@dataclass(frozen=True)
class AIC:
    """An ACPs Agent Identity Code.

    Attributes:
        arsp: Agent Registration Service Provider identifier.
        provider_id: Organization provider identifier.
        ontology_seq: Ontology (class-level) sequence number.
        entity_seq: Entity (instance-level) sequence, Base36 string.
        version: Schema version.
        checksum: AUTOSAR CRC-16/CCITT-FALSE checksum, Base36 encoded.
    """

    arsp: str
    provider_id: str
    ontology_seq: str
    entity_seq: str
    version: str
    checksum: str

    @property
    def aic_string(self) -> str:
        """Full AIC identifier as a dot-separated OID string."""
        return ".".join(
            [
                AIC_OID_ROOT,
                self.arsp,
                self.provider_id,
                self.ontology_seq,
                self.entity_seq,
                self.version,
                self.checksum,
            ]
        )

    @property
    def is_ontology(self) -> bool:
        """True if this AIC represents an Ontology (class-level), False for Entity."""
        return self.entity_seq == "0"

    @classmethod
    def parse(cls, aic_string: str) -> AIC:
        """Parse an AIC string into an :class:`AIC` instance.

        Args:
            aic_string: The dot-separated AIC identifier.

        Returns:
            The parsed :class:`AIC`.

        Raises:
            ValueError: If the string is not a valid AIC.
        """
        match = _AIC_PATTERN.match(aic_string)
        if match is None:
            raise ValueError(f"Invalid AIC format: {aic_string}")
        arsp, provider, onto, entity, version, checksum = match.groups()
        return cls(
            arsp=arsp,
            provider_id=provider,
            ontology_seq=onto,
            entity_seq=entity.lower(),
            version=version,
            checksum=checksum.lower(),
        )

    @classmethod
    def generate(
        cls,
        arsp: str = DEFAULT_ARSP,
        provider_id: str = "1",
        ontology_seq: str = "1",
        version: str = "1",
    ) -> AIC:
        """Generate a new Entity AIC with a random entity sequence.

        Args:
            arsp: ARSP identifier.
            provider_id: Provider organization identifier.
            ontology_seq: Parent ontology sequence.
            version: Schema version.

        Returns:
            A new :class:`AIC` instance with computed checksum.
        """
        entity_seq = _generate_entity_seq()
        checksum = compute_aic_checksum(
            arsp=arsp,
            provider_id=provider_id,
            ontology_seq=ontology_seq,
            entity_seq=entity_seq,
            version=version,
        )
        return cls(
            arsp=arsp,
            provider_id=provider_id,
            ontology_seq=ontology_seq,
            entity_seq=entity_seq,
            version=version,
            checksum=checksum,
        )

    def verify(self) -> bool:
        """Verify that this AIC's checksum is correct.

        Returns:
            True if the checksum matches, False otherwise.
        """
        expected = compute_aic_checksum(
            arsp=self.arsp,
            provider_id=self.provider_id,
            ontology_seq=self.ontology_seq,
            entity_seq=self.entity_seq,
            version=self.version,
        )
        return _constant_time_eq(self.checksum, expected)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "arsp": self.arsp,
            "provider_id": self.provider_id,
            "ontology_seq": self.ontology_seq,
            "entity_seq": self.entity_seq,
            "version": self.version,
            "checksum": self.checksum,
            "aic_string": self.aic_string,
            "is_ontology": self.is_ontology,
        }


class AICIdentityAdapter:
    """Bidirectional mapper between MAREF DID and ACPs AIC identifiers.

    Maintains an in-memory mapping table for DID ↔ AIC translation. The
    mapping is one-to-one: each MAREF DID corresponds to exactly one AIC
    Entity, and the mapping is persisted for the lifetime of the adapter
    instance.
    """

    def __init__(self) -> None:
        self._did_to_aic: dict[AgentDID, AIC] = {}
        self._aic_to_did: dict[str, AgentDID] = {}

    def register(
        self,
        did: AgentDID,
        aic: AIC,
    ) -> AIC:
        """Register a DID-to-AIC mapping.

        Args:
            did: The MAREF DID to register.
            aic: Pre-computed AIC to bind to this DID. Use :meth:`register_new`
                to generate a new AIC automatically.

        Returns:
            The AIC bound to this DID.

        Raises:
            ValueError: If the AIC checksum is invalid, or the DID is already
                registered with a different AIC, or the AIC is already bound
                to a different DID.
        """
        if not aic.verify():
            raise ValueError(f"AIC checksum verification failed: {aic.aic_string}")

        existing = self._did_to_aic.get(did)
        if existing is not None and existing.aic_string != aic.aic_string:
            raise ValueError(
                f"DID {did.did_string} already registered with AIC {existing.aic_string}"
            )

        aic_key = aic.aic_string
        existing_did = self._aic_to_did.get(aic_key)
        if existing_did is not None and existing_did != did:
            raise ValueError(
                f"AIC {aic_key} already bound to DID {existing_did.did_string}"
            )

        self._did_to_aic[did] = aic
        self._aic_to_did[aic_key] = did
        return aic

    def register_new(
        self,
        did: AgentDID,
        arsp: str = DEFAULT_ARSP,
        provider_id: str = "1",
        ontology_seq: str = "1",
        version: str = "1",
    ) -> AIC:
        """Generate and register a new AIC for a DID."""
        aic = AIC.generate(
            arsp=arsp,
            provider_id=provider_id,
            ontology_seq=ontology_seq,
            version=version,
        )
        return self.register(did, aic)

    def did_to_aic(self, did: AgentDID) -> AIC | None:
        """Resolve the AIC bound to a MAREF DID."""
        return self._did_to_aic.get(did)

    def unregister(self, did: AgentDID) -> AIC | None:
        """Remove a DID ↔ AIC mapping.

        Args:
            did: The MAREF DID to unregister.

        Returns:
            The removed AIC if found, None otherwise.
        """
        aic = self._did_to_aic.pop(did, None)
        if aic is not None:
            self._aic_to_did.pop(aic.aic_string, None)
        return aic

    def aic_to_did(self, aic: AIC) -> AgentDID | None:
        """Resolve the MAREF DID bound to an AIC."""
        return self._aic_to_did.get(aic.aic_string)

    def translate_did_to_aic_string(self, did_string: str) -> str:
        """Translate a DID string to its AIC string.

        Args:
            did_string: The MAREF DID string.

        Returns:
            The corresponding AIC string.

        Raises:
            ValueError: If the DID string is invalid or unmapped.
        """
        did = AgentDID.parse(did_string)
        aic = self._did_to_aic.get(did)
        if aic is None:
            raise ValueError(f"No AIC mapping for DID: {did_string}")
        return aic.aic_string

    def translate_aic_string_to_did(self, aic_string: str) -> str:
        """Translate an AIC string to its DID string.

        Args:
            aic_string: The ACPs AIC string.

        Returns:
            The corresponding MAREF DID string.

        Raises:
            ValueError: If the AIC string is invalid or unmapped.
        """
        aic = AIC.parse(aic_string)
        did = self._aic_to_did.get(aic.aic_string)
        if did is None:
            raise ValueError(f"No DID mapping for AIC: {aic_string}")
        return did.did_string

    def list_mappings(self) -> list[dict[str, str]]:
        """Return all registered DID ↔ AIC mappings."""
        return [
            {"did": did.did_string, "aic": aic.aic_string}
            for did, aic in self._did_to_aic.items()
        ]

    @property
    def mapping_count(self) -> int:
        """Number of registered DID ↔ AIC mappings."""
        return len(self._did_to_aic)


# ---------------------------------------------------------------------------
# CRC-16/CCITT-FALSE (AUTOSAR variant) implementation
# ---------------------------------------------------------------------------

# CRC-16/CCITT-FALSE parameters:
#   polynomial = 0x1021, initial = 0xFFFF, no reflection, xorout = 0x0000.
_CRC16_POLY = 0x1021
_CRC16_INIT = 0xFFFF


def _crc16_ccitt_false(data: bytes) -> int:
    """Compute CRC-16/CCITT-FALSE (AUTOSAR) checksum.

    Args:
        data: Input bytes.

    Returns:
        16-bit checksum as an integer.
    """
    crc = _CRC16_INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ _CRC16_POLY
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def compute_aic_checksum(
    arsp: str,
    provider_id: str,
    ontology_seq: str,
    entity_seq: str,
    version: str,
) -> str:
    """Compute the AIC checksum (Base36 encoded CRC-16/CCITT-FALSE).

    The checksum is computed over the OID payload (all AIC fields except
    the checksum itself) using AUTOSAR CRC-16/CCITT-FALSE, then Base36
    encoded. This matches the ACPs AIC v2.00 specification for cross-system
    interoperability. AIC checksums are not salted.

    Args:
        arsp: ARSP identifier.
        provider_id: Provider identifier.
        ontology_seq: Ontology sequence.
        entity_seq: Entity sequence (Base36).
        version: Schema version.

    Returns:
        Base36-encoded CRC-16 checksum string (lowercase, no padding).
    """
    payload_str = ".".join(
        [AIC_OID_ROOT, arsp, provider_id, ontology_seq, entity_seq, version]
    )
    crc = _crc16_ccitt_false(payload_str.encode("utf-8"))
    return _base36_encode(crc)


def _base36_encode(value: int) -> str:
    """Encode a non-negative integer as a Base36 string (lowercase)."""
    if value < 0:
        raise ValueError("Base36 input must be non-negative")
    if value == 0:
        return "0"
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    result: list[str] = []
    while value > 0:
        value, rem = divmod(value, 36)
        result.append(chars[rem])
    return "".join(reversed(result))


def _generate_entity_seq() -> str:
    """Generate a random entity sequence (Base36, fixed length)."""
    # Generate a random integer in [0, 36^9) and encode as Base36.
    max_value = 36 ** _ENTITY_SEQ_LENGTH
    value = secrets.randbelow(max_value)
    encoded = _base36_encode(value)
    # Left-pad with '0' to maintain fixed length.
    return encoded.rjust(_ENTITY_SEQ_LENGTH, "0")


def _constant_time_eq(a: str, b: str) -> bool:
    """Constant-time string comparison to mitigate timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


__all__ = [
    "AIC",
    "AICIdentityAdapter",
    "AIC_OID_ROOT",
    "DEFAULT_ARSP",
    "compute_aic_checksum",
]
