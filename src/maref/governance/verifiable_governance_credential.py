"""Verifiable Governance Credential — 可离线验证的治理合规凭证。

将治理状态（state_machine/drift/consensus/memory/audit 各维度）打包为
Ed25519 签名的凭证，携带联邦 Merkle 包含性证明。监管方无需接入 MAREF
即可离线验证：签名有效 + 未过期 + 未吊销 + Merkle 包含。

设计: docs/plans/2026-08-01-agent-war-governance-design.md 方案 B
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.eivl.federated_merkle import FederatedProof
from maref.signing.signing_key import ReportSigningKey

# 治理维度清单：凭证声称覆盖的治理面
GOVERNANCE_SCOPES = ("state_machine", "drift", "consensus", "memory", "audit")


@dataclass
class VerifiableGovernanceCredential:
    """一个治理主体的可验证治理凭证。

    Attributes:
        credential_id: 凭证唯一标识。
        subject_did: 治理主体（agent/组织）的 DID。
        issuer_did: 签发方 DID。
        scope: 覆盖的治理维度（GOVERNANCE_SCOPES 子集）。
        merkle_proof: 指向某次审计区块的 FederatedProof dict。
        valid_from: 生效时间（unix 秒）。
        expires_at: 过期时间（unix 秒）。
        signature: Ed25519 签名（base64）。
        signer_public_key_pem: 签发方公钥（验证用）。
    """

    credential_id: str
    subject_did: str
    issuer_did: str
    scope: list[str]
    merkle_proof: dict[str, Any]
    valid_from: float
    expires_at: float
    signature: str = ""
    signer_public_key_pem: str = ""
    compliance_mapping: dict[str, Any] = field(default_factory=dict)

    # -- 签发 --

    @classmethod
    def issue(
        cls,
        subject_did: str,
        issuer_did: str,
        scope: list[str],
        merkle_proof: FederatedProof | dict[str, Any],
        signing_key: ReportSigningKey,
        ttl_seconds: float = 86400,
    ) -> VerifiableGovernanceCredential:
        """以 Ed25519 私钥签发治理凭证。

        merkle_proof 可为 FederatedProof 对象或等价 dict；不传则生成空证明，
        验证时跳过 Merkle 包含性检查（非完整治理凭证）。
        """
        for dim in scope:
            if dim not in GOVERNANCE_SCOPES:
                raise ValueError(f"未知治理维度: {dim!r}")
        proof_dict = (
            merkle_proof.to_dict() if isinstance(merkle_proof, FederatedProof) else merkle_proof
        )
        now = time.time()
        cred = cls(
            credential_id=f"vgc-{secrets.token_hex(8)}",
            subject_did=subject_did,
            issuer_did=issuer_did,
            scope=list(scope),
            merkle_proof=proof_dict,
            valid_from=now,
            expires_at=now + ttl_seconds,
        )
        cred.signature = signing_key.sign_report(cred._signing_payload())
        cred.signer_public_key_pem = signing_key.public_key_pem
        return cred

    # -- 验证 --

    def verify_signature(self) -> bool:
        """离线验证 Ed25519 签名与所携带公钥是否匹配。"""
        if not self.signature or not self.signer_public_key_pem:
            return False
        return ReportSigningKey.verify_signature(
            self.signer_public_key_pem, self.signature, self._signing_payload()
        )

    def verify_merkle_inclusion(self) -> bool:
        """离线验证 Merkle 包含性证明（无 merkle_proof 时返回 True）。"""
        if not self.merkle_proof:
            return True
        try:
            return FederatedProof.from_dict(self.merkle_proof).verify()
        except (KeyError, TypeError, ValueError):
            return False

    def is_expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) > self.expires_at

    def attach_compliance_mapping(
        self,
        mapping: dict[str, Any],
        signing_key: Any | None = None,
    ) -> None:
        """附加按辖区的合规映射（v0.45.0 方案 G G3）。

        ``mapping`` 结构::

            {
              "jurisdiction": "eu",
              "profile_name": "European Union — AI Act + GDPR",
              "actions": {
                 "payment:transfer": {"enforcement": "enforce", "regulations": ["eu_ai_act"]},
                 "file.read": {"enforcement": "observe", "regulations": []},
              }
            }

        mapping 纳入签名 payload，作为对监管的可验证合规证明输出——
        篡改 enforcement/regulations 会被 ``verify_signature`` 检测。
        已签名凭证需传 ``signing_key`` 重签，否则 mapping 不被签名覆盖。
        """
        self.compliance_mapping = mapping
        if signing_key is not None:
            self.signature = signing_key.sign_report(self._signing_payload())
            self.signer_public_key_pem = signing_key.public_key_pem

    def renew(self, signing_key: ReportSigningKey, ttl_seconds: float = 86400) -> None:
        """就地续期：保留 credential_id 与 Merkle 证明，重算有效期并重签名。

        用于治理状态未变、仅需延长对外有效期的场景；治理状态已变更应
        用 refresh(新证明) 重新签发而非 renew。
        """
        now = time.time()
        self.valid_from = now
        self.expires_at = now + ttl_seconds
        self.signature = signing_key.sign_report(self._signing_payload())
        self.signer_public_key_pem = signing_key.public_key_pem

    def refresh(
        self,
        merkle_proof: FederatedProof | dict[str, Any],
        signing_key: ReportSigningKey,
        ttl_seconds: float = 86400,
    ) -> None:
        """以新审计证明刷新凭证，反映最新治理状态；保留 credential_id 以保证可追溯。"""
        self.merkle_proof = (
            merkle_proof.to_dict() if isinstance(merkle_proof, FederatedProof) else merkle_proof
        )
        self.renew(signing_key, ttl_seconds=ttl_seconds)

    def verify(
        self,
        now: float | None = None,
        revoked: bool = False,
        require_merkle: bool = False,
    ) -> dict[str, Any]:
        """全量验证，返回逐项结果供审计/对外展示。

        返回:
            {valid, signature_valid, merkle_valid, expired, revoked}
        """
        cur = now if now is not None else time.time()
        sig_ok = self.verify_signature()
        merkle_ok = self.verify_merkle_inclusion()
        expired = self.is_expired(cur)
        result = {
            "valid": sig_ok and merkle_ok and not expired and not revoked,
            "signature_valid": sig_ok,
            "merkle_valid": merkle_ok,
            "expired": expired,
            "revoked": revoked,
        }
        if require_merkle and not self.merkle_proof:
            result["valid"] = False
        return result

    # -- 序列化 --

    def _signing_payload(self) -> bytes:
        body = {
            "credential_id": self.credential_id,
            "subject_did": self.subject_did,
            "issuer_did": self.issuer_did,
            "scope": self.scope,
            "merkle_proof": self.merkle_proof,
            "valid_from": self.valid_from,
            "expires_at": self.expires_at,
            "compliance_mapping": self.compliance_mapping,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "subject_did": self.subject_did,
            "issuer_did": self.issuer_did,
            "scope": self.scope,
            "merkle_proof": self.merkle_proof,
            "valid_from": self.valid_from,
            "expires_at": self.expires_at,
            "signature": self.signature,
            "signer_public_key_pem": self.signer_public_key_pem,
            "compliance_mapping": dict(self.compliance_mapping),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerifiableGovernanceCredential:
        return cls(
            credential_id=data["credential_id"],
            subject_did=data["subject_did"],
            issuer_did=data["issuer_did"],
            scope=list(data["scope"]),
            merkle_proof=data.get("merkle_proof", {}),
            valid_from=float(data["valid_from"]),
            expires_at=float(data["expires_at"]),
            signature=data.get("signature", ""),
            signer_public_key_pem=data.get("signer_public_key_pem", ""),
            compliance_mapping=dict(data.get("compliance_mapping", {})),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, data: str) -> VerifiableGovernanceCredential:
        return cls.from_dict(json.loads(data))

    def to_file(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_file(cls, path: str | Path) -> VerifiableGovernanceCredential:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


class GovernanceCredentialStore:
    """治理凭证仓库：存储、吊销、有效期过滤、持久化。

    吊销仅记录 credential_id + 原因 + 来源（保留历史，不删除）。source
    字段为方案 E 的 DID 撤销事件联动预留（如 "did-revocation:did:maref/...")。
    """

    def __init__(self) -> None:
        self._credentials: dict[str, VerifiableGovernanceCredential] = {}
        self._revoked: dict[str, str] = {}
        self._revoked_sources: dict[str, str] = {}

    def store(self, cred: VerifiableGovernanceCredential) -> None:
        self._credentials[cred.credential_id] = cred

    def get(self, credential_id: str) -> VerifiableGovernanceCredential | None:
        return self._credentials.get(credential_id)

    def revoke(self, credential_id: str, reason: str = "unspecified", source: str = "") -> None:
        if credential_id not in self._credentials:
            raise ValueError(f"凭证 {credential_id} 不存在")
        self._revoked[credential_id] = reason
        if source:
            self._revoked_sources[credential_id] = source

    def revoke_by_subject_did(
        self,
        subject_did: str,
        reason: str = "did_revoked",
        source: str = "",
    ) -> int:
        """吊销指定治理主体的全部有效凭证（方案 E M3 联动）。

        当 DID 撤销事件到达时，将该主体所有凭证（含已吊销的除外）
        一并吊销，确保吊销列表与 DID 生命周期一致。

        Args:
            subject_did: 治理主体 DID（如 ``did:maref:default:abcd1234``）。
            reason: 吊销原因。
            source: 触发来源，默认 ``did-revocation:{subject_did}``。

        Returns:
            本次新吊销的凭证数量（已吊销的不重复计数）。
        """
        source = source or f"did-revocation:{subject_did}"
        count = 0
        for cid, cred in list(self._credentials.items()):
            if cred.subject_did == subject_did and not self.is_revoked(cid):
                self._revoked[cid] = reason
                self._revoked_sources[cid] = source
                count += 1
        return count

    def attach_to_did_registry(
        self,
        registry: Any,
        server_id: str = "",
    ) -> None:
        """绑定 DIDRegistry：其 DID 撤销/停用事件自动联动吊销凭证。

        通过订阅 registry 的撤销监听器，任意主体 DID 被撤销时，
        该主体的治理凭证立即进入吊销列表（并保留 ``did-revocation`` 来源）。

        Args:
            registry: 实现了 ``add_revocation_listener(listener)`` 的 DIDRegistry。
            server_id: 预留的服务器标识（未使用，保留签名兼容）。
        """
        registry.add_revocation_listener(self._on_did_revocation)

    def _on_did_revocation(self, did_string: str, reason: str, signer: str) -> None:
        self.revoke_by_subject_did(
            subject_did=did_string,
            reason=f"did_revoked:{reason}" if reason else "did_revoked",
            source=f"did-revocation:{did_string}",
        )

    def is_revoked(self, credential_id: str) -> bool:
        return credential_id in self._revoked

    def revoked_reason(self, credential_id: str) -> str | None:
        return self._revoked.get(credential_id)

    def revoked_source(self, credential_id: str) -> str | None:
        return self._revoked_sources.get(credential_id)

    def revocation_list(self) -> dict[str, str]:
        return dict(self._revoked)

    def build_signed_revocation_list(
        self, signing_key: ReportSigningKey, server_id: str = ""
    ) -> dict[str, Any]:
        """构造带签发方 Ed25519 签名的吊销列表，防离线篡改。

        签名覆盖 {server_id, revoked, signed_at} 规范 JSON；验证方
        用 :meth:`verify_signed_revocation_list` 离线核验即可确认
        吊销列表未被篡改（与凭证签名闭环对齐）。
        """
        body: dict[str, Any] = {
            "server_id": server_id,
            "revoked": self.revocation_list(),
            "signed_at": time.time(),
        }
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        body["signature"] = signing_key.sign_report(payload)
        body["signer_public_key_pem"] = signing_key.public_key_pem
        return body

    @classmethod
    def verify_signed_revocation_list(cls, data: dict[str, Any]) -> bool:
        """离线验证签名吊销列表（signature/signer_public_key_pem 缺失视为无效）。"""
        sig = data.get("signature", "")
        pub = data.get("signer_public_key_pem", "")
        if not sig or not pub:
            return False
        body = {k: v for k, v in data.items() if k not in ("signature", "signer_public_key_pem")}
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        return ReportSigningKey.verify_signature(pub, sig, payload)

    def list_valid(self, now: float | None = None) -> list[VerifiableGovernanceCredential]:
        cur = now if now is not None else time.time()
        return [
            c
            for c in self._credentials.values()
            if not self.is_revoked(c.credential_id)
            and not c.is_expired(cur)
            and c.verify_signature()
        ]

    # -- 持久化 --

    def to_dict(self) -> dict[str, Any]:
        return {
            "credentials": {cid: c.to_dict() for cid, c in self._credentials.items()},
            "revoked": dict(self._revoked),
            "revoked_sources": dict(self._revoked_sources),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernanceCredentialStore:
        store = cls()
        for cid, cdata in data.get("credentials", {}).items():
            store._credentials[cid] = VerifiableGovernanceCredential.from_dict(cdata)
        store._revoked = dict(data.get("revoked", {}))
        store._revoked_sources = dict(data.get("revoked_sources", {}))
        return store

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, data: str) -> GovernanceCredentialStore:
        return cls.from_dict(json.loads(data))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> GovernanceCredentialStore:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def save_revocation_list(self, path: str | Path) -> None:
        """仅导出吊销列表（不含凭证全文），供外部监管/审计方消费。"""
        Path(path).write_text(json.dumps(self.to_dict()["revoked"], indent=2), encoding="utf-8")

    def save_signed_revocation_list(
        self, path: str | Path, signing_key: ReportSigningKey, server_id: str = ""
    ) -> None:
        """导出带 Ed25519 签名的吊销列表，防篡改。"""
        Path(path).write_text(
            json.dumps(self.build_signed_revocation_list(signing_key, server_id), indent=2),
            encoding="utf-8",
        )

    def load_revocation_list(self, path: str | Path) -> None:
        """以权威快照覆盖本地吊销表（外部列表是全量真值，非增量）。"""
        self._revoked = dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def load_signed_revocation_list(self, path: str | Path) -> dict[str, Any]:
        """读取并校验签名吊销列表，无效时抛 ValueError；有效则覆盖本地吊销表。"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not self.verify_signed_revocation_list(data):
            raise ValueError("revocation list signature invalid")
        self._revoked = dict(data.get("revoked", {}))
        return data

    def count(self) -> int:
        return len(self._credentials)

    def revoked_count(self) -> int:
        return len(self._revoked)

    def revoked_count_for_subject(self, subject_did: str) -> int:
        """统计某治理主体当前被吊销的凭证数量（供撤销联动报告）。"""
        return sum(
            1
            for cid in self._revoked
            if self._credentials.get(cid) is not None
            and self._credentials[cid].subject_did == subject_did
        )
