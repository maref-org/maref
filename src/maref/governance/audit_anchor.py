"""审计外部锚定 — 把审计历史的批量 Merkle 根落到仓库之外。

哈希链能发现就地篡改，但无法发现"整段历史被删除并重算新链"。
本模块按批量策略（满 N 条或满 T 秒）为审计记录生成 Merkle 锚点：

- 叶子哈希绑定每条审计记录的完整 JSON 内容（含 metadata 与签名）；
- 锚点文件是仓库外的 append-only JSONL，由部署侧保管；
- 可选 RFC 3161 时间戳令牌（``tsa`` 回调返回 ASCII/Base64 字符串）。
  TSA 不可用时 fail-open：锚点照常落盘，写入高优先级审计事件并告警，
  不阻塞治理裁决。

校验时按 ``batch_start_id`` / ``batch_end_id`` 定位连续批次，重算 Merkle
根并与锚点比对；删除中间事件、修改 payload、删除整段历史后重写审计链
都会导致不一致。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.governance.audit import AuditLogger

logger = logging.getLogger(__name__)

TSA_FAILURE_EVENT = "audit_anchor_tsa_unavailable"


class AuditAnchorError(ValueError):
    """锚定输入不可用或已损坏时抛出（fail-closed）。"""


@dataclass(frozen=True)
class AnchorRecord:
    """一个批次锚点，对应审计日志中一段连续记录。"""

    batch_start_id: str
    batch_end_id: str
    merkle_root: str
    event_count: int
    tsa_token: str = ""
    anchored_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.batch_start_id or not self.batch_end_id:
            raise ValueError("anchor batch ids are required")
        if self.event_count <= 0:
            raise ValueError("event_count must be positive")
        if len(self.merkle_root) != 64:
            raise ValueError("merkle_root must be a 64-character SHA-256 hex digest")
        try:
            bytes.fromhex(self.merkle_root)
        except ValueError as exc:
            raise ValueError("merkle_root must be hexadecimal") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_start_id": self.batch_start_id,
            "batch_end_id": self.batch_end_id,
            "merkle_root": self.merkle_root,
            "event_count": self.event_count,
            "tsa_token": self.tsa_token,
            "anchored_at": self.anchored_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AnchorRecord:
        try:
            return cls(
                batch_start_id=str(data["batch_start_id"]),
                batch_end_id=str(data["batch_end_id"]),
                merkle_root=str(data["merkle_root"]),
                event_count=int(data["event_count"]),
                tsa_token=str(data.get("tsa_token", "")),
                anchored_at=float(data.get("anchored_at", 0.0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid anchor record: {exc}") from exc


@dataclass(frozen=True)
class AnchorVerifyReport:
    """锚点校验结果。``ok=False`` 时 ``issues`` 说明不一致位置。"""

    audit_path: str
    anchors_path: str
    ok: bool
    issues: list[str] = field(default_factory=list)
    anchor_count: int = 0
    anchored_events: int = 0
    total_events: int = 0
    uncovered_events: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_path": self.audit_path,
            "anchors_path": self.anchors_path,
            "ok": self.ok,
            "issues": list(self.issues),
            "anchor_count": self.anchor_count,
            "anchored_events": self.anchored_events,
            "total_events": self.total_events,
            "uncovered_events": self.uncovered_events,
        }


def _canonical_record(record: Mapping[str, Any]) -> bytes:
    return json.dumps(
        record,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def record_leaf_hash(record: Mapping[str, Any]) -> str:
    """整条审计记录的规范 JSON 哈希；任一字段变化都会改变叶子。"""
    return hashlib.sha256(_canonical_record(record)).hexdigest()


def merkle_root(records: Iterable[Mapping[str, Any]]) -> str:
    """计算有序记录的 Merkle 根；空批次返回空串，奇数层复制末节点。"""
    level = [record_leaf_hash(record) for record in records]
    if not level:
        return ""
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256((level[index] + level[index + 1]).encode("utf-8")).hexdigest()
            for index in range(0, len(level), 2)
        ]
    return level[0]


def _load_audit_records(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], []
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"audit line {lineno}: {exc}")
                continue
            if not isinstance(data, dict) or not data.get("id"):
                issues.append(f"audit line {lineno}: invalid record")
                continue
            records.append(data)
    return records, issues


def _load_anchors(path: Path) -> tuple[list[AnchorRecord], list[str]]:
    if not path.exists():
        return [], []
    anchors: list[AnchorRecord] = []
    issues: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"anchors line {lineno}: {exc}")
                continue
            if not isinstance(data, dict):
                issues.append(f"anchors line {lineno}: invalid anchor record")
                continue
            try:
                anchors.append(AnchorRecord.from_dict(data))
            except ValueError as exc:
                issues.append(f"anchors line {lineno}: {exc}")
    return anchors, issues


def verify_anchors(
    audit_path: Path | str,
    anchors_path: Path | str,
) -> AnchorVerifyReport:
    """按锚点重算批量 Merkle 根并校验连续性（fail-closed）。"""
    audit = Path(audit_path)
    anchors_file = Path(anchors_path)
    issues: list[str] = []
    if not audit.exists():
        issues.append(f"audit file not found: {audit}")
    if not anchors_file.exists():
        issues.append(f"anchors file not found: {anchors_file}")

    records, audit_issues = _load_audit_records(audit)
    anchors, anchor_issues = _load_anchors(anchors_file)
    issues.extend(audit_issues)
    issues.extend(anchor_issues)
    if not anchors and not anchor_issues:
        issues.append("no anchor records")

    index_by_id: dict[str, int] = {}
    for index, record in enumerate(records):
        record_id = str(record.get("id", ""))
        if record_id in index_by_id:
            issues.append(f"duplicate audit id {record_id!r}")
            continue
        index_by_id[record_id] = index

    previous_end = -1
    anchor_count = 0
    anchored_events = 0
    for anchor in anchors:
        start = index_by_id.get(anchor.batch_start_id)
        end = index_by_id.get(anchor.batch_end_id)
        if start is None:
            issues.append(f"anchor batch start {anchor.batch_start_id!r} not found in audit log")
            continue
        if end is None:
            issues.append(f"anchor batch end {anchor.batch_end_id!r} not found in audit log")
            continue
        if end < start:
            issues.append(
                f"anchor batch {anchor.batch_start_id!r}..{anchor.batch_end_id!r} is out of order"
            )
            continue
        if start != previous_end + 1:
            issues.append("anchored batches are not contiguous from the start of the audit log")
        batch = records[start : end + 1]
        if len(batch) != anchor.event_count:
            issues.append(
                f"batch {anchor.batch_start_id}..{anchor.batch_end_id} has {len(batch)} events, "
                f"expected {anchor.event_count}"
            )
        if merkle_root(batch) != anchor.merkle_root:
            issues.append(
                f"merkle root mismatch for batch {anchor.batch_start_id}..{anchor.batch_end_id}"
            )
        previous_end = end
        anchor_count += 1
        anchored_events += anchor.event_count

    total_events = len(records)
    uncovered_events = max(total_events - (previous_end + 1), 0)
    return AnchorVerifyReport(
        audit_path=str(audit),
        anchors_path=str(anchors_file),
        ok=not issues,
        issues=issues,
        anchor_count=anchor_count,
        anchored_events=anchored_events,
        total_events=total_events,
        uncovered_events=uncovered_events,
    )


class AuditAnchor:
    """按批量策略为审计日志生成 Merkle 锚点。

    Args:
        audit_path: 审计 JSONL 路径。
        anchors_path: 锚点 JSONL 路径（应位于仓库之外，由部署侧保管）。
        batch_size: 满多少条记录触发一次锚定。
        batch_seconds: 距上次锚定超过多少秒且有未锚定记录时触发。
        tsa: 可选时间戳回调，接收 Merkle 根、返回令牌字符串。
        alert: TSA 不可用时的告警回调。
        audit: 可选 :class:`AuditLogger`，用于写入锚定事件。
        now: 可注入的时钟，便于测试。
    """

    def __init__(
        self,
        audit_path: Path | str,
        anchors_path: Path | str,
        *,
        batch_size: int = 100,
        batch_seconds: float = 300.0,
        tsa: Callable[[str], str] | None = None,
        alert: Callable[[str], None] | None = None,
        audit: AuditLogger | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if batch_seconds <= 0:
            raise ValueError("batch_seconds must be > 0")
        self._audit_path = Path(audit_path)
        self._anchors_path = Path(anchors_path)
        self._batch_size = int(batch_size)
        self._batch_seconds = float(batch_seconds)
        self._tsa = tsa
        self._alert = alert
        self._audit = audit
        self._now = now
        self._started_at = float(now())

    @property
    def pending_count(self) -> int:
        """尚无锚点的审计记录数。"""
        records = self._read_audit_strict()
        anchors = self._read_anchors_strict()
        return len(self._pending(records, anchors))

    def anchors(self) -> list[AnchorRecord]:
        """已落盘的锚点。"""
        return self._read_anchors_strict()

    def maybe_anchor(self, *, now: float | None = None) -> AnchorRecord | None:
        """满足满 N 条或满 T 秒时锚定一个批次，否则返回 None。"""
        timestamp = self._now() if now is None else float(now)
        records = self._read_audit_strict()
        anchors = self._read_anchors_strict()
        pending = self._pending(records, anchors)
        if not pending:
            return None
        last_anchored = anchors[-1].anchored_at if anchors else self._started_at
        if len(pending) < self._batch_size and timestamp - last_anchored < self._batch_seconds:
            return None
        return self._anchor_batch(pending[: self._batch_size], timestamp)

    def anchor_now(self, *, now: float | None = None) -> list[AnchorRecord]:
        """强制把当前所有未锚定记录按批次落盘。"""
        timestamp = self._now() if now is None else float(now)
        records = self._read_audit_strict()
        anchors = self._read_anchors_strict()
        pending = self._pending(records, anchors)
        created: list[AnchorRecord] = []
        for start in range(0, len(pending), self._batch_size):
            batch = pending[start : start + self._batch_size]
            created.append(self._anchor_batch(batch, timestamp))
        return created

    def _read_audit_strict(self) -> list[dict[str, Any]]:
        if not self._audit_path.exists():
            raise AuditAnchorError(f"audit file not found: {self._audit_path}")
        records, issues = _load_audit_records(self._audit_path)
        if issues:
            raise AuditAnchorError("; ".join(issues))
        return records

    def _read_anchors_strict(self) -> list[AnchorRecord]:
        anchors, issues = _load_anchors(self._anchors_path)
        if issues:
            raise AuditAnchorError("; ".join(issues))
        return anchors

    @staticmethod
    def _pending(
        records: list[dict[str, Any]],
        anchors: list[AnchorRecord],
    ) -> list[dict[str, Any]]:
        if not anchors:
            return records
        end_id = anchors[-1].batch_end_id
        for index, record in enumerate(records):
            if record.get("id") == end_id:
                return records[index + 1 :]
        raise AuditAnchorError(f"anchored batch end {end_id!r} not found in audit log")

    def _anchor_batch(
        self,
        batch: list[dict[str, Any]],
        timestamp: float,
    ) -> AnchorRecord:
        root = merkle_root(batch)
        token = ""
        error = ""
        if self._tsa is not None:
            try:
                token = str(self._tsa(root) or "").strip()
            except Exception as exc:  # TSA 故障不得阻塞治理裁决
                error = f"{type(exc).__name__}: {exc}"
            if not token and not error:
                error = "TSA returned no token"
        record = AnchorRecord(
            batch_start_id=str(batch[0]["id"]),
            batch_end_id=str(batch[-1]["id"]),
            merkle_root=root,
            event_count=len(batch),
            tsa_token=token,
            anchored_at=timestamp,
        )
        self._append_anchor(record)
        if error:
            self._report_tsa_failure(record, error)
        return record

    def _append_anchor(self, record: AnchorRecord) -> None:
        self._anchors_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._anchors_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")

    def _report_tsa_failure(self, record: AnchorRecord, error: str) -> None:
        message = (
            f"audit anchor TSA unavailable; batch "
            f"{record.batch_start_id}..{record.batch_end_id} was anchored without "
            f"a timestamp token ({error})"
        )
        if self._audit is not None:
            self._audit.log(
                event_type=TSA_FAILURE_EVENT,
                actor="AuditAnchor",
                action="anchor",
                details=message,
                metadata={
                    "priority": "high",
                    "alert": True,
                    "batch_start_id": record.batch_start_id,
                    "batch_end_id": record.batch_end_id,
                    "merkle_root": record.merkle_root,
                    "event_count": record.event_count,
                    "tsa_error": error,
                },
            )
        if self._alert is not None:
            try:
                self._alert(message)
            except Exception:
                logger.exception("audit anchor alert callback failed")
        logger.error(message)


__all__ = [
    "TSA_FAILURE_EVENT",
    "AnchorRecord",
    "AnchorVerifyReport",
    "AuditAnchor",
    "AuditAnchorError",
    "merkle_root",
    "record_leaf_hash",
    "verify_anchors",
]
