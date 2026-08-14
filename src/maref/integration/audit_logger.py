"""audit_logger.py — MCP Audit Log persistence with JSONL + HMAC signing.

DEPRECATED: Use ``maref.governance.audit_bus.AuditBus`` instead.
AuditBus provides the same HMAC-signed JSONL persistence as a unified
interface.  Migration::

    from maref.governance.audit_bus import AuditBus

    # instead of: from maref.integration.audit_logger import AuditLogger
    bus = AuditBus()

This module is frozen (no new features, bug fixes only). It remains for
backward compatibility with existing MCP audit log files.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AuditRecord:
    """A single audit log record."""

    timestamp: float
    agent_id: str
    mcp_server: str
    tool_name: str
    verdict: str
    args_hash: str
    risk_score: float = 0.0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "timestamp": self.timestamp,
                "agent_id": self.agent_id,
                "mcp_server": self.mcp_server,
                "tool_name": self.tool_name,
                "verdict": self.verdict,
                "args_hash": self.args_hash,
                "risk_score": self.risk_score,
                "latency_ms": self.latency_ms,
                **self.metadata,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditRecord:
        return cls(
            timestamp=data["timestamp"],
            agent_id=data["agent_id"],
            mcp_server=data["mcp_server"],
            tool_name=data["tool_name"],
            verdict=data["verdict"],
            args_hash=data["args_hash"],
            risk_score=data.get("risk_score", 0.0),
            latency_ms=data.get("latency_ms", 0.0),
            metadata={
                k: v
                for k, v in data.items()
                if k
                not in (
                    "timestamp",
                    "agent_id",
                    "mcp_server",
                    "tool_name",
                    "verdict",
                    "args_hash",
                    "risk_score",
                    "latency_ms",
                )
            },
        )


class AuditLogger:
    """Persistent MCP audit logger with HMAC signing.

    Logs to data/audit/mcp_audit.jsonl with HMAC-SHA256 signatures.
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        hmac_secret: bytes | None = None,
        max_file_size_mb: int = 50,
    ) -> None:
        repo_root = self._find_repo_root()
        self.log_dir = log_dir or repo_root / "data" / "audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        _hmac_secret = hmac_secret or os.environb.get(b"MAREF_HMAC_SECRET_KEY")
        if _hmac_secret is None:
            # Try loading from key file (same fallback as governance/audit.py)
            for _key_path in (".maraf_hmac_key", ".gaas_api_key"):
                try:
                    with open(_key_path) as _f:
                        _hmac_secret = _f.read().strip().encode("utf-8")
                        break
                except (FileNotFoundError, OSError):
                    continue
        if _hmac_secret is None:
            import logging

            logging.getLogger(__name__).warning(
                "No HMAC secret configured - MCP audit logging tamper protection disabled. "
                "Set MAREF_HMAC_SECRET_KEY env var or create .maraf_hmac_key file."
            )
        self.hmac_secret = _hmac_secret
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self._current_log_file = self.log_dir / "mcp_audit.jsonl"

    def log_call(
        self,
        agent_id: str,
        mcp_server: str,
        tool_name: str,
        verdict: str,
        args: dict[str, Any] | None = None,
        risk_score: float = 0.0,
        latency_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> AuditRecord:
        args_hash = hashlib.sha256(json.dumps(args or {}, sort_keys=True).encode()).hexdigest()[:16]

        record = AuditRecord(
            timestamp=time.time(),
            agent_id=agent_id,
            mcp_server=mcp_server,
            tool_name=tool_name,
            verdict=verdict,
            args_hash=args_hash,
            risk_score=risk_score,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )

        self._rotate_if_needed()
        line = record.to_json_line()
        signature = self._sign(record)

        with open(self._current_log_file, "a") as f:
            f.write(f"{line}\t{signature}\n")

        return record

    def query(
        self,
        agent_id: str | None = None,
        mcp_server: str | None = None,
        tool_name: str | None = None,
        verdict: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        results: list[AuditRecord] = []
        if not self._current_log_file.exists():
            return results

        with open(self._current_log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.rsplit("\t", 1)
                if len(parts) != 2:
                    continue
                try:
                    data = json.loads(parts[0])
                    record = AuditRecord.from_dict(data)
                except (json.JSONDecodeError, KeyError):
                    continue

                if agent_id and record.agent_id != agent_id:
                    continue
                if mcp_server and record.mcp_server != mcp_server:
                    continue
                if tool_name and record.tool_name != tool_name:
                    continue
                if verdict and record.verdict != verdict:
                    continue
                results.append(record)
                if len(results) >= limit:
                    break

        return results

    def verify_integrity(self) -> dict[str, Any]:
        total = 0
        valid = 0
        if not self._current_log_file.exists():
            return {"status": "no_file", "verified": True}

        with open(self._current_log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.rsplit("\t", 1)
                if len(parts) != 2:
                    continue
                total += 1
                try:
                    data = json.loads(parts[0])
                    record = AuditRecord.from_dict(data)
                    expected = self._sign(record)
                    if hmac.compare_digest(expected, parts[1]):
                        valid += 1
                except (json.JSONDecodeError, KeyError):
                    pass

        invalid = total - valid
        return {
            "status": "verified" if invalid == 0 else "tampered",
            "total": total,
            "valid": valid,
            "invalid": invalid,
        }

    def get_stats(self, window_hours: float = 24.0) -> dict[str, Any]:
        cutoff = time.time() - (window_hours * 3600)
        records = self.query(limit=10000)
        records = [r for r in records if r.timestamp >= cutoff]

        total = len(records)
        allowed = sum(1 for r in records if r.verdict == "ALLOW")
        denied = sum(1 for r in records if r.verdict == "DENY")

        return {
            "total": total,
            "allowed": allowed,
            "denied": denied,
            "window_hours": window_hours,
        }

    def _rotate_if_needed(self) -> None:
        if self._current_log_file.exists():
            size = self._current_log_file.stat().st_size
            if size >= self.max_file_size_bytes:
                from datetime import datetime, timezone

                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                rotated = self._current_log_file.with_name(f"mcp_audit_{ts}.jsonl")
                self._current_log_file.rename(rotated)
                self._current_log_file = self.log_dir / "mcp_audit.jsonl"

    def _sign(self, record: AuditRecord) -> str:
        if self.hmac_secret is None:
            return ""
        payload = json.dumps(
            {
                "timestamp": record.timestamp,
                "agent_id": record.agent_id,
                "mcp_server": record.mcp_server,
                "tool_name": record.tool_name,
                "verdict": record.verdict,
                "args_hash": record.args_hash,
            },
            sort_keys=True,
        )
        return hmac.new(self.hmac_secret, payload.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _find_repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
                return parent
        return current.parent.parent.parent


_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
