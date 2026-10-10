"""人工审批防篡改台账（框架 3.0 附件2 二.3(3)）。

《人工智能安全治理框架3.0》附件2 二.3(3) 要求：
    "采用防篡改、可校验的方式保存人工审批日志"——
    审批记录须绑定审批人身份、可离线校验、任何篡改可被检出。

本模块提供 ``ApprovalLedger``：
- **链式哈希**：每条记录 ``chain_hash = H(prev_hash || canonical_payload)``，
  任何历史记录被改动都会破坏其后的链；
- **数字签名（fail-closed）**：优先国密 SM2（``crypto/sm2.sm2_sign``），
  回退 Ed25519（``crypto/ed25519_keys.Ed25519KeyPair``）；签名失败即拒绝写入；
- **Merkle 可离线验证**：复用 ``eivl/merkle_auditor``，生成 ``MerkleProof``，
  proof 可由第三方仅凭 ``merkle_hash_pair`` 独立验证；
- **审批人身份绑定**：可选注入身份服务（``is_active(did)``），
  非 active 审批人拒绝记账；
- **fail-closed 阻断**：``require_record`` / ``enforce_high_risk``
  在缺记录时抛错，供高风险操作前置校验（与 ApprovalEngine 接线点）。

设计: docs/plans/2026-10-02-maref-framework-3-0-compliance-mapping-plan.md P1
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from maref.eivl.merkle_auditor import AuditEvidence, MerkleAuditor, MerkleProof

# SM2 依赖 gmssl，缺失时回退 Ed25519
try:  # pragma: no cover - 取决于运行环境是否安装 gmssl
    from maref.crypto.sm2 import SM2KeyPair, sm2_sign, sm2_verify

    HAS_SM2 = True
except Exception:  # noqa: BLE001
    SM2KeyPair = None  # type: ignore[assignment]
    sm2_sign = None  # type: ignore[assignment]
    sm2_verify = None  # type: ignore[assignment]
    HAS_SM2 = False

SIG_SM2 = "sm2"
SIG_ED25519 = "ed25519"

DECISION_APPROVED = "approved"
DECISION_DENIED = "denied"
VALID_DECISIONS = (DECISION_APPROVED, DECISION_DENIED)

HIGH_RISK_LEVELS = ("high", "critical", "重大", "特别重大")

_GENESIS_HASH = "0" * 64


class ApprovalLedgerError(RuntimeError):
    """台账操作失败（签名/校验/持久化）。fail-closed 语义。"""


class ApprovalMissingError(ApprovalLedgerError):
    """高风险操作缺少人工审批记录——阻断执行。"""


class IdentityServiceProtocol(Protocol):
    """身份服务最小契约（duck typing，避免强耦合）。"""

    def is_active(self, did_string: str) -> bool: ...


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ApprovalRecord:
    """一条人工审批记录（内容 + 链式哈希 + 数字签名）。"""

    record_id: str
    approver_id: str
    action: str
    decision: str
    rationale: str
    timestamp: float
    risk_level: str
    previous_hash: str
    chain_hash: str
    signature: str
    signature_type: str
    signer_public_key: str
    approver_did: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    merkle_evidence_hash: str = ""

    def signing_payload(self) -> dict[str, Any]:
        """签名/链哈希覆盖的确定性载荷（不含签名与 Merkle 字段）。"""
        return {
            "record_id": self.record_id,
            "approver_id": self.approver_id,
            "approver_did": self.approver_did,
            "action": self.action,
            "decision": self.decision,
            "rationale": self.rationale,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "previous_hash": self.previous_hash,
            "metadata": self.metadata,
        }

    def compute_chain_hash(self) -> str:
        return _sha256_hex(self.previous_hash + "|" + _canonical(self.signing_payload()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalRecord:
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class ApprovalLedger:
    """防篡改人工审批台账（链式哈希 + 签名 + Merkle + 可选持久化）。"""

    def __init__(
        self,
        *,
        signing_public_key: str = "",
        signing_private_key: str = "",
        signature_type: str = SIG_ED25519,
        ed25519_keypair: Any | None = None,
        sm2_keypair: Any | None = None,
        identity_service: IdentityServiceProtocol | None = None,
        storage_path: str | Path | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._records: list[ApprovalRecord] = []
        self._merkle = MerkleAuditor()
        self._identity_service = identity_service
        self._storage_path = Path(storage_path) if storage_path else None

        self._signature_type = signature_type
        self._ed25519_keypair = ed25519_keypair
        self._sm2_keypair = sm2_keypair
        self._ed25519_public_key = signing_public_key
        self._sm2_private_key = signing_private_key
        self._sm2_public_key = signing_public_key

        if signature_type == SIG_SM2 and not self._sm2_public_key and sm2_keypair is not None:
            self._sm2_public_key = sm2_keypair.public_key
        if (
            signature_type == SIG_ED25519
            and not self._ed25519_public_key
            and ed25519_keypair is not None
        ):
            self._ed25519_public_key = ed25519_keypair.public_key_pem

        if self._storage_path and self._storage_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # 记账
    # ------------------------------------------------------------------

    def record(
        self,
        approver_id: str,
        action: str,
        decision: str,
        rationale: str = "",
        *,
        risk_level: str = "low",
        approver_did: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalRecord:
        """写入一条审批记录。签名失败或审批人非法即 fail-closed 拒绝。"""
        if decision not in VALID_DECISIONS:
            raise ApprovalLedgerError(f"非法审批结论: {decision!r}（仅 {VALID_DECISIONS}）")
        if not approver_id:
            raise ApprovalLedgerError("approver_id 不能为空（审批人身份不可缺省）")

        if approver_did and self._identity_service is not None:
            try:
                active = self._identity_service.is_active(approver_did)
            except Exception as exc:  # noqa: BLE001 - 身份系统异常一律 fail-closed
                raise ApprovalLedgerError(f"身份校验异常，拒绝记账: {exc}") from exc
            if not active:
                raise ApprovalLedgerError(f"审批人 DID 非 active，拒绝记账: {approver_did}")

        with self._lock:
            previous_hash = self._records[-1].chain_hash if self._records else _GENESIS_HASH
            record = ApprovalRecord(
                record_id=uuid.uuid4().hex,
                approver_id=approver_id,
                action=action,
                decision=decision,
                rationale=rationale,
                timestamp=time.time(),
                risk_level=risk_level,
                previous_hash=previous_hash,
                chain_hash="",
                signature="",
                signature_type=self._signature_type,
                signer_public_key="",
                approver_did=approver_did,
                metadata=metadata or {},
            )
            record.chain_hash = record.compute_chain_hash()
            signature, signer_public_key = self._sign(record.chain_hash)
            record.signature = signature
            record.signer_public_key = signer_public_key

            evidence_hash = self._append_evidence(record)
            record.merkle_evidence_hash = evidence_hash

            self._records.append(record)
            self._persist(record)
            return record

    def safe_record(
        self,
        approver_id: str,
        action: str,
        *,
        risk_level: str = "low",
        approver_did: str = "",
        metadata: dict[str, Any] | None = None,
        exc: BaseException | None = None,
    ) -> ApprovalRecord:
        """审批执行异常时的兜底：记录 denied 且不执行（fail-closed）。"""
        reason = f"审批系统异常，默认拒绝: {exc}" if exc else "审批系统异常，默认拒绝"
        return self.record(
            approver_id=approver_id or "system",
            action=action,
            decision=DECISION_DENIED,
            rationale=reason,
            risk_level=risk_level,
            approver_did=approver_did,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # 签名（SM2 优先，Ed25519 回退）
    # ------------------------------------------------------------------

    def _sign(self, chain_hash: str) -> tuple[str, str]:
        data = chain_hash.encode("utf-8")
        if self._signature_type == SIG_SM2:
            if not HAS_SM2:
                raise ApprovalLedgerError("SM2 签名要求 gmssl，但当前环境不可用")
            private_key = (
                self._sm2_private_key
                or getattr(  # gitleaks:allow（运行时取值，非硬编码密钥）
                    self._sm2_keypair, "private_key", ""
                )
            )
            public_key = self._sm2_public_key or getattr(self._sm2_keypair, "public_key", "")
            if not private_key or not public_key:
                raise ApprovalLedgerError("SM2 模式缺少密钥对")
            # gmssl 使用随机 k，极少数情况下会产出不可验签结果 → 自校验后重签，fail-closed。
            for _ in range(3):
                signature = sm2_sign(private_key, data, public_key)
                if sm2_verify(public_key, data, signature):
                    return signature, public_key
            raise ApprovalLedgerError("SM2 签名自校验连续 3 次失败，拒绝写入")

        if self._ed25519_keypair is None:
            raise ApprovalLedgerError("Ed25519 模式缺少密钥对")
        signature = self._ed25519_keypair.sign(data)
        return signature.hex(), self._ed25519_keypair.public_key_pem

    @staticmethod
    def _verify(signature_type: str, public_key: str, chain_hash: str, signature: str) -> bool:
        data = chain_hash.encode("utf-8")
        try:
            if signature_type == SIG_SM2:
                if not HAS_SM2:
                    return False
                return sm2_verify(public_key, data, signature)
            from maref.crypto.ed25519_keys import Ed25519KeyPair

            return Ed25519KeyPair.verify(public_key, bytes.fromhex(signature), data)
        except Exception:  # noqa: BLE001 - 任何验签异常视为不可信
            return False

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    def verify_record(self, record: ApprovalRecord, previous_hash: str) -> bool:
        """校验单条记录：链哈希 + 签名。"""
        if record.previous_hash != previous_hash:
            return False
        if record.chain_hash != record.compute_chain_hash():
            return False
        return self._verify(
            record.signature_type, record.signer_public_key, record.chain_hash, record.signature
        )

    def verify_chain(self, records: list[ApprovalRecord] | None = None) -> bool:
        """逐条校验链完整性；任一记录被篡改即返回 False。"""
        items = records if records is not None else self._records
        previous_hash = _GENESIS_HASH
        for record in items:
            if not self.verify_record(record, previous_hash):
                return False
            previous_hash = record.chain_hash
        return True

    # ------------------------------------------------------------------
    # Merkle
    # ------------------------------------------------------------------

    def _append_evidence(self, record: ApprovalRecord) -> str:
        evidence = AuditEvidence(
            evidence_id=record.record_id,
            timestamp=record.timestamp,
            evidence_type="human_approval",
            source_agent=record.approver_id,
            target_agent=None,
            action=record.action,
            result={
                "decision": record.decision,
                "risk_level": record.risk_level,
                "chain_hash": record.chain_hash,
            },
            previous_hash=record.previous_hash,
            nonce=0,
        )
        return self._merkle.add_evidence(evidence)

    def get_merkle_proof(self, record_id: str) -> MerkleProof | None:
        record = self.get_record(record_id)
        if record is None or not record.merkle_evidence_hash:
            return None
        return self._merkle.generate_proof(record.merkle_evidence_hash)

    def merkle_root(self) -> str | None:
        return self._merkle.get_root_hash()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @property
    def records(self) -> list[ApprovalRecord]:
        return list(self._records)

    def get_record(self, record_id: str) -> ApprovalRecord | None:
        for record in self._records:
            if record.record_id == record_id:
                return record
        return None

    def records_for_action(self, action: str) -> list[ApprovalRecord]:
        return [r for r in self._records if r.action == action]

    def require_record(self, action: str) -> ApprovalRecord:
        """高风险操作前置校验：必须有 approved 记录，否则 fail-closed 阻断。"""
        approved = [
            r for r in self._records if r.action == action and r.decision == DECISION_APPROVED
        ]
        if not approved:
            raise ApprovalMissingError(f"高风险操作缺少人工审批记录，阻断执行: {action}")
        return approved[-1]

    def enforce_high_risk(self, action: str, risk_level: str) -> ApprovalRecord | None:
        """仅高风险级别强制要求审批记录；非高风险返回 None。"""
        if risk_level in HIGH_RISK_LEVELS:
            return self.require_record(action)
        return None

    # ------------------------------------------------------------------
    # 持久化（append-only JSONL）
    # ------------------------------------------------------------------

    def _persist(self, record: ApprovalRecord) -> None:
        if not self._storage_path:
            return
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with self._storage_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            raise ApprovalLedgerError(f"台账持久化失败: {exc}") from exc

    def _load(self) -> None:
        if not self._storage_path or not self._storage_path.exists():
            return
        with self._storage_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = ApprovalRecord.from_dict(json.loads(line))
                self._records.append(record)
                self._append_evidence(record)

    def summary(self) -> dict[str, Any]:
        approved = sum(1 for r in self._records if r.decision == DECISION_APPROVED)
        denied = sum(1 for r in self._records if r.decision == DECISION_DENIED)
        return {
            "total": len(self._records),
            "approved": approved,
            "denied": denied,
            "chain_valid": self.verify_chain(),
            "merkle_root": self.merkle_root(),
            "signature_type": self._signature_type,
        }


def _extract_action_id(request: Any) -> str:
    if isinstance(request, dict):
        for key in ("action", "tool_name", "name", "action_id"):
            if request.get(key):
                return str(request[key])
        return "unknown"
    for attr in ("action", "tool_name", "name", "action_id"):
        if hasattr(request, attr):
            return str(getattr(request, attr))
    return "unknown"


def _is_high_risk(risk: Any) -> bool:
    if risk is None:
        return False
    value = getattr(risk, "value", risk)
    text = str(value)
    return text.lower() in ("high", "critical") or text in HIGH_RISK_LEVELS


def integrate_with_approval_engine(
    engine: Any,
    ledger: ApprovalLedger,
    *,
    action_from_request: Any | None = None,
) -> Any:
    """把台账接入 ApprovalEngine：高风险决策必须具备人工审批记录，否则阻断。

    非侵入式运行时包装——保留原 ``engine.predict`` 语义，仅在其返回高风险决策时
    追加 ``ledger.require_record`` 校验（fail-closed）。返回包装后的 predict 函数。

    集成点：docs/plans/2026-10-02-maref-framework-3-0-compliance-mapping-plan.md P1。
    """
    original_predict = engine.predict
    extractor = action_from_request or _extract_action_id

    def guarded_predict(request: Any, *args: Any, **kwargs: Any) -> Any:
        decision = original_predict(request, *args, **kwargs)
        if _is_high_risk(getattr(decision, "risk_level", None)):
            ledger.require_record(extractor(request))
        return decision

    engine.predict = guarded_predict
    return guarded_predict


__all__ = [
    "ApprovalLedger",
    "ApprovalLedgerError",
    "ApprovalMissingError",
    "ApprovalRecord",
    "DECISION_APPROVED",
    "DECISION_DENIED",
    "HIGH_RISK_LEVELS",
    "HAS_SM2",
    "SIG_ED25519",
    "SIG_SM2",
    "integrate_with_approval_engine",
]
