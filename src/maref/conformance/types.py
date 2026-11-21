"""Types and canonical hashing for the MAREF conformance suite.

The suite is deliberately stdlib-only: it must be runnable against *any*
agent runtime's exported evidence, without installing MAREF or its
dependencies.  Canonical JSON rules mirror the ones used by the governance
audit chain so that hashes can be compared across implementations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SPEC_VERSION = "0.1"


class Status(str, Enum):
    """Outcome of a single control."""

    PASS = "pass"
    FAIL = "fail"
    NA = "not_applicable"


@dataclass(frozen=True)
class Finding:
    """A single, reproducible violation."""

    message: str
    seq: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "message": self.message}


@dataclass
class ControlResult:
    """Result of one control over one trace."""

    id: str
    title: str
    status: Status
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass
class Report:
    """Signed, portable result of a conformance run."""

    run_id: str
    controls: list[ControlResult]
    generated_at: str
    spec_version: str = SPEC_VERSION
    trace_sha256: str = ""
    signature: dict[str, Any] | None = None

    @property
    def applicable(self) -> list[ControlResult]:
        return [control for control in self.controls if control.status is not Status.NA]

    @property
    def passed(self) -> int:
        return sum(1 for control in self.applicable if control.status is Status.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for control in self.applicable if control.status is Status.FAIL)

    @property
    def score(self) -> float:
        total = len(self.applicable)
        return round(self.passed / total, 4) if total else 0.0

    @property
    def conformant(self) -> bool:
        return bool(self.applicable) and self.failed == 0

    @property
    def verdict(self) -> str:
        return "conformant" if self.conformant else "non_conformant"

    def to_dict(self, include_signature: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "spec_version": self.spec_version,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "trace_sha256": self.trace_sha256,
            "verdict": self.verdict,
            "score": self.score,
            "summary": {
                "pass": self.passed,
                "fail": self.failed,
                "not_applicable": len(self.controls) - len(self.applicable),
                "total": len(self.controls),
            },
            "controls": [control.to_dict() for control in self.controls],
        }
        if include_signature:
            payload["signature"] = self.signature
        return payload


def canonical_bytes(value: Any) -> bytes:
    """Strict canonical JSON (sorted keys, no whitespace, UTF-8)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(value: Any) -> str:
    """``sha256:<hex>`` digest of a canonical JSON value."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def event_digest(event: dict[str, Any]) -> str:
    """Digest of an event excluding its own ``hash`` field."""
    body = {key: value for key, value in event.items() if key != "hash"}
    return sha256_hex(body)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
