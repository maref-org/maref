"""Provenance labels + information-flow control — IFC-lite (P1-5).

对齐 LLMbda Calculus（2026，Lean TIPNI 定理）的思路：给值/消息打 provenance 标签，
规约时传播标签；高风险动作要求输入不源自不可信内容（或经**签名 endorsement** 显式
降级），把 prompt-injection 类目标劫持（OWASP ASI01）从"检测"升级为"结构性不可能"。

标签格（按可信度）::

    TRUSTED / ENDORSED   (clean)
    MIXED                (derived from both clean and tainted)
    UNTRUSTED            (tainted)

join 规则：clean ∧ clean = TRUSTED；相等保持；其余混合 = MIXED。
``ENDORSED`` 必须经 Ed25519 签名（:class:`Endorsement`）——``TaintTracker.set`` 拒绝
直接写 ENDORSED，agent 无法自我降级；未知值 fail-closed 视为 ``UNTRUSTED``。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.security.decorators import security_critical


class ProvenanceLabel(str, Enum):
    """Trust label attached to a value or message."""

    TRUSTED = "trusted"
    ENDORSED = "endorsed"
    MIXED = "mixed"
    UNTRUSTED = "untrusted"


_CLEAN: frozenset[ProvenanceLabel] = frozenset({ProvenanceLabel.TRUSTED, ProvenanceLabel.ENDORSED})


def is_clean_label(label: ProvenanceLabel | str) -> bool:
    """Whether a label is clean (trusted/endorsed); unknown values fail-closed."""
    try:
        parsed = ProvenanceLabel(label)
    except ValueError:
        return False
    return parsed in _CLEAN


def join_labels(a: ProvenanceLabel | str, b: ProvenanceLabel | str) -> ProvenanceLabel:
    """Combine two labels under the provenance lattice."""
    left = ProvenanceLabel(a)
    right = ProvenanceLabel(b)
    if left == right:
        return left
    if left in _CLEAN and right in _CLEAN:
        return ProvenanceLabel.TRUSTED
    return ProvenanceLabel.MIXED


def join_all(labels: Iterable[ProvenanceLabel | str]) -> ProvenanceLabel:
    """Combine many labels (empty → TRUSTED, i.e. no tainted input)."""
    items = [ProvenanceLabel(label) for label in labels]
    if not items:
        return ProvenanceLabel.TRUSTED
    result = items[0]
    for label in items[1:]:
        result = join_labels(result, label)
    return result


@dataclass
class TaintRecord:
    """A tracked value's provenance."""

    value_id: str
    label: ProvenanceLabel
    source: str = ""


class TaintTracker:
    """Tracks provenance labels and propagates them through value lineage."""

    def __init__(self) -> None:
        self._records: dict[str, TaintRecord] = {}

    def set(self, value_id: str, label: ProvenanceLabel | str, source: str = "") -> TaintRecord:
        """Record a label; ENDORSED must go through a signed endorsement."""
        parsed = ProvenanceLabel(label)
        if parsed == ProvenanceLabel.ENDORSED:
            raise ValueError(
                "ENDORSED requires a signed endorsement; use InformationFlowGate.endorse()"
            )
        record = TaintRecord(value_id=value_id, label=parsed, source=source)
        self._records[value_id] = record
        return record

    def _force_set(self, value_id: str, label: ProvenanceLabel, source: str = "") -> None:
        """Internal: set a label bypassing the ENDORSED guard (endorsement only)."""
        self._records[value_id] = TaintRecord(value_id=value_id, label=label, source=source)

    def label_of(self, value_id: str) -> ProvenanceLabel:
        """Label of a value; unknown values are UNTRUSTED (fail-closed)."""
        record = self._records.get(value_id)
        return record.label if record is not None else ProvenanceLabel.UNTRUSTED

    def get(self, value_id: str) -> TaintRecord | None:
        """Raw record, if tracked."""
        return self._records.get(value_id)

    def derive(self, output_id: str, input_ids: Iterable[str], source: str = "") -> ProvenanceLabel:
        """Record ``output_id`` as the join of its inputs' labels; return it."""
        joined = join_all(self.label_of(input_id) for input_id in input_ids)
        self._records[output_id] = TaintRecord(output_id, joined, source)
        return joined

    def clear(self) -> None:
        """Drop all tracked provenance."""
        self._records.clear()

    @property
    def count(self) -> int:
        """Number of tracked values."""
        return len(self._records)


@dataclass
class Endorsement:
    """A signed statement that a value is safe to treat as trusted."""

    value_id: str
    endorser: str
    signature: str = ""

    def canonical_payload(self) -> bytes:
        """Canonical bytes the endorser signs over."""
        return f"{self.value_id}\n{self.endorser}".encode()

    def sign(self, signing_key: Any) -> None:
        """Sign with the endorser's Ed25519 key."""
        self.signature = signing_key.sign_report(self.canonical_payload())

    @security_critical
    def verify(self, public_key_pem: str) -> bool:
        """Verify the endorsement signature against the endorser's public key."""
        if not self.signature or not public_key_pem:
            return False
        from maref.signing.signing_key import ReportSigningKey

        return ReportSigningKey.verify_signature(
            public_key_pem, self.signature, self.canonical_payload()
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "value_id": self.value_id,
            "endorser": self.endorser,
            "signature": self.signature,
        }


@dataclass
class FlowDecision:
    """Result of an information-flow check."""

    allowed: bool
    reason: str = ""
    offending: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "offending": list(self.offending),
        }


class InformationFlowGate:
    """Gate that decides whether an action's inputs are clean enough to proceed."""

    def __init__(self, tracker: TaintTracker | None = None) -> None:
        self._tracker = tracker if tracker is not None else TaintTracker()
        self._endorser_keys: dict[str, str] = {}

    @property
    def tracker(self) -> TaintTracker:
        """Underlying provenance tracker."""
        return self._tracker

    def register_endorser(self, endorser: str, public_key_pem: str) -> None:
        """Register the public key allowed to endorse values."""
        if not endorser or not public_key_pem:
            raise ValueError("endorser and public_key_pem are required")
        self._endorser_keys[endorser] = public_key_pem

    def endorse(self, value_id: str, endorser: str, signing_key: Any) -> Endorsement:
        """Sign and apply an endorsement, marking the value ENDORSED."""
        endorsement = Endorsement(value_id=value_id, endorser=endorser)
        endorsement.sign(signing_key)
        self._tracker._force_set(value_id, ProvenanceLabel.ENDORSED, endorser)
        return endorsement

    @security_critical
    def apply_endorsement(
        self, endorsement: Endorsement, public_key_pem: str | None = None
    ) -> bool:
        """Verify an endorsement and, if valid, mark the value ENDORSED."""
        key = public_key_pem or self._endorser_keys.get(endorsement.endorser)
        if key is None or not endorsement.verify(key):
            return False
        self._tracker._force_set(
            endorsement.value_id, ProvenanceLabel.ENDORSED, endorsement.endorser
        )
        return True

    def check(self, input_ids: Iterable[str]) -> FlowDecision:
        """Require all inputs to be clean; otherwise deny with offenders listed."""
        offending = [
            value_id
            for value_id in input_ids
            if not is_clean_label(self._tracker.label_of(value_id))
        ]
        if offending:
            return FlowDecision(
                allowed=False,
                reason="inputs derive from untrusted content",
                offending=offending,
            )
        return FlowDecision(allowed=True, reason="inputs clean")
