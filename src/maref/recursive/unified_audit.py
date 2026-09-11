from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_DEFAULT_HMAC_KEY: bytes | None = None


def _get_default_hmac_key() -> bytes:
    """获取默认 HMAC 密钥：优先环境变量，否则进程级随机（仅单进程有效）。

    使用模块级缓存确保同一进程内所有未指定密钥的实例使用相同密钥，
    避免序列化后 reload 时签名验证失败。
    """
    global _DEFAULT_HMAC_KEY
    if _DEFAULT_HMAC_KEY is not None:
        return _DEFAULT_HMAC_KEY
    key = os.environ.get("MAREF_AUDIT_HMAC_KEY") or os.urandom(32).hex()
    _DEFAULT_HMAC_KEY = key.encode("utf-8")
    return _DEFAULT_HMAC_KEY


@dataclass
class UnifiedAuditRecord:
    record_id: str
    timestamp: float
    layer: str
    round: int
    event_type: str
    source_module: str
    target_module: str
    decision: str
    justification: str
    outcome: str | None = None
    context_refs: list[str] = field(default_factory=list)
    tenant_id: str = ""
    # 修复 P0-4：新增 signature 字段，HMAC-SHA256 签名
    signature: str = ""

    def _payload_for_signing(self) -> str:
        """签名载荷：覆盖所有业务字段（排除 signature 自身）。"""
        return (
            f"{self.record_id}|{self.timestamp}|{self.layer}|{self.round}|"
            f"{self.event_type}|{self.source_module}|{self.target_module}|"
            f"{self.decision}|{self.justification}|{self.outcome}|"
            f"{','.join(self.context_refs)}"
        )

    def sign(self, hmac_key: bytes) -> None:
        """使用 HMAC-SHA256 签名本记录（原地修改 signature 字段）。"""
        payload = self._payload_for_signing().encode("utf-8")
        self.signature = hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()

    def verify(self, hmac_key: bytes) -> bool:
        """验证签名完整性。无签名时返回 False。"""
        if not self.signature:
            return False
        payload = self._payload_for_signing().encode("utf-8")
        expected = hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "layer": self.layer,
            "round": self.round,
            "event_type": self.event_type,
            "source_module": self.source_module,
            "target_module": self.target_module,
            "decision": self.decision,
            "justification": self.justification,
            "outcome": self.outcome,
            "context_refs": self.context_refs,
            "tenant_id": self.tenant_id,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnifiedAuditRecord:
        return cls(
            record_id=data["record_id"],
            timestamp=data["timestamp"],
            layer=data["layer"],
            round=data["round"],
            event_type=data["event_type"],
            source_module=data["source_module"],
            target_module=data["target_module"],
            decision=data["decision"],
            justification=data["justification"],
            outcome=data.get("outcome"),
            context_refs=data.get("context_refs", []),
            tenant_id=data.get("tenant_id", ""),
            signature=data.get("signature", ""),
        )


class NullAuditStore:
    """No-op audit store for dev/test. Drops all records silently."""

    def append(self, record: UnifiedAuditRecord) -> None:
        pass

    def query_by_layer(self, layer: str) -> list[UnifiedAuditRecord]:
        return []

    def query_by_event(self, event_type: str) -> list[UnifiedAuditRecord]:
        return []

    def query_by_module(self, module: str) -> list[UnifiedAuditRecord]:
        return []


class UnifiedAuditStore:
    """Audit store with optional JSON file persistence.

    When *persist_path* is provided, every append() also writes to the
    JSON lines (`.jsonl`) file so data survives process restarts.
    """

    def __init__(
        self,
        persist_path: str | Path | None = None,
        hmac_key: bytes | None = None,
        max_file_size_mb: int = 50,
        max_backup_files: int = 5,
        max_age_days: int = 90,
        audit_bus: Any = None,
    ) -> None:
        self._records: list[UnifiedAuditRecord] = []
        self._by_layer: dict[str, list[int]] = defaultdict(list)
        self._by_module: dict[str, list[int]] = defaultdict(list)
        self._by_event_type: dict[str, list[int]] = defaultdict(list)
        self._by_round: dict[int, list[int]] = defaultdict(list)
        # 可选的 AuditBus 扇出（与新版本 API 兼容）；持久化仍走 HMAC 文件
        self._audit_bus = audit_bus
        self._persist_path: Path | None = (
            Path(persist_path) if persist_path else None
        )
        # 修复 P0-4：HMAC 密钥，未提供时使用默认（环境变量或进程随机）
        self._hmac_key: bytes = hmac_key if hmac_key is not None else _get_default_hmac_key()
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self._max_backup_files = max_backup_files
        self._max_age_days = max_age_days
        self._lock: threading.RLock = threading.RLock()
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    # ── public API ──────────────────────────────────────────────

    def append(self, record: UnifiedAuditRecord) -> None:
        with self._lock:
            if not record.signature:
                record.sign(self._hmac_key)
            idx = len(self._records)
            self._records.append(record)
            self._by_layer[record.layer].append(idx)
            self._by_module[record.source_module].append(idx)
            self._by_module[record.target_module].append(idx)
            self._by_event_type[record.event_type].append(idx)
            self._by_round[record.round].append(idx)
            if self._persist_path:
                self._append_to_disk(record)
            if self._audit_bus is not None:
                try:
                    self._audit_bus.log_from_unified(record)
                except Exception:
                    pass

    def verify_all_signatures(self) -> dict[str, Any]:
        """验证所有记录的签名完整性（修复 P0-4）。"""
        total = len(self._records)
        valid = 0
        unsigned = 0
        tampered: list[str] = []
        for record in self._records:
            if not record.signature:
                unsigned += 1
                tampered.append(record.record_id)
            elif not record.verify(self._hmac_key):
                tampered.append(record.record_id)
            else:
                valid += 1
        return {
            "total": total,
            "valid": valid,
            "unsigned": unsigned,
            "tampered": tampered,
            "integrity_ok": len(tampered) == 0,
        }

    def query_by_layer(self, layer: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_layer.get(layer, [])]

    def query_by_event(self, event_type: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_event_type.get(event_type, [])]

    def query_by_module(self, module: str) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_module.get(module, [])]

    def query_by_round(self, round_num: int) -> list[UnifiedAuditRecord]:
        return [self._records[i] for i in self._by_round.get(round_num, [])]

    def query_decision_chain(self, record_id: str, max_depth: int = 10) -> list[UnifiedAuditRecord]:
        chain: list[UnifiedAuditRecord] = []
        visited: set[str] = set()
        queue = [record_id]
        depth = 0

        while queue and depth < max_depth:
            rid = queue.pop(0)
            if rid in visited:
                continue
            visited.add(rid)
            depth += 1

            for record in self._records:
                if record.record_id == rid:
                    chain.append(record)
                    for ref in record.context_refs:
                        if ref not in visited:
                            queue.append(ref)
                    break

        return chain

    def stats_by_event_type(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_event_type.items()}

    def stats_by_module(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_module.items()}

    def stats_by_round(self) -> dict[int, int]:
        return {k: len(v) for k, v in self._by_round.items()}

    def count(self) -> int:
        return len(self._records)

    def all(self) -> list[UnifiedAuditRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()
        self._by_layer.clear()
        self._by_module.clear()
        self._by_event_type.clear()
        self._by_round.clear()

    @property
    def persist_path(self) -> Path | None:
        return self._persist_path

    # ── disk persistence ────────────────────────────────────────

    def _rotate_if_needed(self) -> None:
        if not self._persist_path:
            return
        try:
            if not self._persist_path.exists():
                return
            size_bytes = self._persist_path.stat().st_size
            if size_bytes < self._max_file_size_bytes:
                return
        except OSError:
            return
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        backup_name = f"{self._persist_path.stem}.{timestamp}{self._persist_path.suffix}"
        backup_path = self._persist_path.with_name(backup_name)
        try:
            self._persist_path.rename(backup_path)
            self._cleanup_old_backups()
        except OSError as e:
            logger.warning(
                "UnifiedAuditStore rotation failed path=%s error=%s: %s",
                self._persist_path,
                type(e).__name__,
                e,
            )

    def _cleanup_old_backups(self) -> None:
        if not self._persist_path:
            return
        pattern = f"{self._persist_path.stem}.*{self._persist_path.suffix}"
        try:
            backups = sorted(
                self._persist_path.parent.glob(pattern),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in backups[self._max_backup_files:]:
                old.unlink()
        except OSError as e:
            logger.warning(
                "UnifiedAuditStore cleanup failed error=%s: %s",
                type(e).__name__,
                e,
            )

    def _load_from_disk(self) -> None:
        if not self._persist_path:
            return
        files_to_load: list[Path] = []
        pattern = f"{self._persist_path.stem}.*{self._persist_path.suffix}"
        try:
            backups = sorted(
                self._persist_path.parent.glob(pattern),
                key=lambda p: p.stat().st_mtime,
            )
            files_to_load.extend(backups)
            if self._persist_path.exists():
                files_to_load.append(self._persist_path)
        except OSError:
            pass
        for fpath in files_to_load:
            self._load_single_file(fpath)

    def _load_single_file(self, fpath: Path) -> None:
        try:
            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    record = UnifiedAuditRecord.from_dict(data)
                    if not record.verify(self._hmac_key):
                        logger.warning(
                            "UnifiedAuditStore skipping tampered/unsigned record "
                            "path=%s record_id=%s",
                            fpath,
                            record.record_id,
                        )
                        continue
                    idx = len(self._records)
                    self._records.append(record)
                    self._by_layer[record.layer].append(idx)
                    self._by_module[record.source_module].append(idx)
                    self._by_module[record.target_module].append(idx)
                    self._by_event_type[record.event_type].append(idx)
                    self._by_round[record.round].append(idx)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "UnifiedAuditStore load_single_file failed path=%s error=%s: %s",
                fpath,
                type(e).__name__,
                e,
            )

    def verify_saved_file(self, fpath: Path | None = None) -> dict[str, Any]:
        """Validate all signatures in a persisted file (offline verification)."""
        target = fpath or self._persist_path
        if not target:
            return {"valid": 0, "tampered": 0, "total": 0, "integrity_ok": True}
        valid = 0
        tampered = 0
        try:
            with open(target) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    record = UnifiedAuditRecord.from_dict(data)
                    if record.verify(self._hmac_key):
                        valid += 1
                    else:
                        tampered += 1
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "UnifiedAuditStore verify_saved_file failed path=%s error=%s: %s",
                target,
                type(e).__name__,
                e,
            )
            return {"valid": 0, "tampered": 0, "total": 0, "integrity_ok": False}
        total = valid + tampered
        return {
            "valid": valid,
            "tampered": tampered,
            "total": total,
            "integrity_ok": tampered == 0,
        }

    def _append_to_disk(self, record: UnifiedAuditRecord) -> None:
        if self._persist_path is None:
            logger.warning("persist_path is None — skipping disk append")
            return
        self._rotate_if_needed()
        try:
            with open(self._persist_path, "a") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError as e:
            # 问题 4 修复: 磁盘满/权限错误时记录告警，避免审计数据无声丢失
            logger.warning(
                "UnifiedAuditStore append_to_disk failed path=%s error=%s: %s "
                "audit record may be lost (in-memory only)",
                self._persist_path,
                type(e).__name__,
                e,
            )


def make_record_id(prefix: str, counter: int) -> str:
    return f"{prefix}_{counter:06d}_{int(time.time() * 1000)}"


class UnifiedAudit:
    """Stub for backward compatibility — delegates to UnifiedAuditStore."""

    def __init__(self) -> None:
        self.store = UnifiedAuditStore()

    def log(self, record: UnifiedAuditRecord) -> None:
        self.store.append(record)

    def query(self, **kwargs: Any) -> list[UnifiedAuditRecord]:
        q = getattr(self.store, "query", None)
        if callable(q):
            return q(**kwargs)
        return []
