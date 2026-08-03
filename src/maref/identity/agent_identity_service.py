"""AgentIdentityService — Agent 互联网统一身份编排门面（v0.44.0 I3）。

聚合 DIDRegistry + AgentDNS + GovernanceCredentialStore + TrustEngineV2，
对外暴露单一 ``resolve / issue / verify / revoke`` 门面，屏蔽底层模块
的组合复杂度，并确保各生命周期状态保持一致：

- 撤销 DID → 自动联动吊销该主体治理凭证（I1）并使 AgentDNS 能力目录失效。
- 签发凭证前校验 DID 已注册且 active（防无身份签发）。
- resolve 聚合返回 DID 文档 + 能力目录 + 信任评分三重视角。

设计: docs/plans/2026-08-03-v0.44.0-iteration-plan.md I3
"""

from __future__ import annotations

from typing import Any

from maref.governance.verifiable_governance_credential import (
    GovernanceCredentialStore,
    VerifiableGovernanceCredential,
)
from maref.identity.agent_dns import AgentCard, AgentDNS
from maref.identity.did_registry import AgentDID, DIDRegistry
from maref.recursive.trust_engine_v2 import TrustEngineV2
from maref.security.decorators import security_critical


class AgentIdentityService:
    """统一身份编排门面：DID 生命周期 + 能力目录 + 凭证 + 信任。

    Attributes:
        did_registry: DID 注册表（身份生命周期真值源）。
        agent_dns: DID → 能力目录解析服务。
        credential_store: 治理凭证仓库（签发/吊销/验证）。
        trust_engine: 信任引擎（以 DID 字符串为键）。
        signing_key: 默认签发密钥（issue 未显式传入时使用）。
    """

    def __init__(
        self,
        did_registry: DIDRegistry | None = None,
        agent_dns: AgentDNS | None = None,
        credential_store: GovernanceCredentialStore | None = None,
        trust_engine: TrustEngineV2 | None = None,
        signing_key: Any | None = None,
    ) -> None:
        self._did_registry = did_registry or DIDRegistry()
        self._agent_dns = agent_dns or AgentDNS(did_registry=self._did_registry)
        self._credential_store = credential_store or GovernanceCredentialStore()
        self._trust_engine = trust_engine or TrustEngineV2()
        self._signing_key = signing_key
        # 联动：DID 撤销 → 凭证吊销（I1 机制）
        self._credential_store.attach_to_did_registry(self._did_registry)

    # ------------------------------------------------------------------
    # 门面：resolve
    # ------------------------------------------------------------------

    def resolve(self, did_string: str) -> dict[str, Any] | None:
        """聚合解析一个 DID：DID 文档元数据 + 能力目录 + 信任评分。

        返回 None 表示 DID 未注册。聚合各子解析结果（存在缺失时用
        空占位），调用方可根据 ``did.status`` 判定生命周期。
        """
        try:
            did = AgentDID.parse(did_string)
        except ValueError:
            return None
        record = self._did_registry.resolve(did)
        if record is None:
            return None

        doc_result = self._did_registry.resolve_did_document(did)
        card = self._agent_dns.resolve(did)
        score = self._trust_engine.get_score(did_string)
        return {
            "did": did_string,
            "did_document_metadata": doc_result.document_metadata,
            "agent_card": card.to_dict() if card is not None else None,
            "trust": score.to_dict() if score is not None else None,
            "status": record.status,
            "version": record.version,
        }

    def resolve_agent_card(self, did_string: str) -> AgentCard | None:
        """仅解析能力目录（DID 生命周期非 active 返回 None）。"""
        try:
            did = AgentDID.parse(did_string)
        except ValueError:
            return None
        return self._agent_dns.resolve(did)

    # ------------------------------------------------------------------
    # 门面：issue
    # ------------------------------------------------------------------

    @security_critical
    def issue(
        self,
        subject_did: str,
        scope: list[str],
        merkle_proof: dict[str, Any] | None = None,
        ttl_seconds: float = 86400,
        signing_key: Any | None = None,
        jurisdiction: str | None = None,
    ) -> VerifiableGovernanceCredential:
        """为治理主体签发治理凭证。

        要求 DID 已注册且处于 active；否则抛 :class:`ValueError`。
        未提供 signing_key 时使用服务默认密钥（未配置则抛 ValueError）。

        提供 ``jurisdiction`` 时，凭证附带按辖区的合规映射
        （v0.45.0 方案 G G3）——对监管的"证明输出"。
        """
        did = AgentDID.parse(subject_did)
        if self._did_registry.resolve(did) is None:
            raise ValueError(f"DID {subject_did} 未注册，拒绝签发凭证")
        if not self._did_registry.is_active(did):
            raise ValueError(f"DID {subject_did} 生命周期非 active，拒绝签发凭证")

        key = signing_key or self._signing_key
        if key is None:
            raise ValueError("未配置签发密钥：issue 需传入 signing_key 或服务默认密钥")

        # 防御纵深：若该 DID 已注册公钥，签发密钥必须与其匹配（防冒名签发）。
        record = self._did_registry.resolve(did)
        registered_key = record.ed25519_public_key() if record is not None else ""
        if registered_key and key.public_key_pem != registered_key:
            raise ValueError(
                f"签发密钥与该 DID 注册公钥不匹配，拒绝签发凭证: {subject_did}"
            )

        cred = VerifiableGovernanceCredential.issue(
            subject_did=subject_did,
            issuer_did=did.did_string,
            scope=scope,
            merkle_proof=merkle_proof or {},
            signing_key=key,
            ttl_seconds=ttl_seconds,
        )
        if jurisdiction:
            from maref.compliance.regulatory_policy_mapper import RegulatoryPolicyMapper

            cred.attach_compliance_mapping(
                RegulatoryPolicyMapper().build_credential_mapping(
                    scopes=scope, jurisdiction=jurisdiction
                ),
                signing_key=key,
            )
        self._credential_store.store(cred)
        return cred

    # ------------------------------------------------------------------
    # 门面：verify
    # ------------------------------------------------------------------

    @security_critical
    def verify(
        self,
        credential: VerifiableGovernanceCredential,
        now: float | None = None,
        require_merkle: bool = False,
    ) -> dict[str, Any]:
        """验证凭证：签名 + Merkle 包含 + 有效期 + 吊销状态。"""
        revoked = self._credential_store.is_revoked(credential.credential_id)
        result = credential.verify(
            now=now,
            revoked=revoked,
            require_merkle=require_merkle,
        )
        # 防御纵深：subject DID 生命周期非 active 时凭证亦不可信。
        if result["valid"] and not self.is_active(credential.subject_did):
            result["valid"] = False
            result["subject_inactive"] = True
        result["credential_id"] = credential.credential_id
        result["subject_did"] = credential.subject_did
        result["revoked_reason"] = self._credential_store.revoked_reason(
            credential.credential_id
        )
        return result

    # ------------------------------------------------------------------
    # 门面：revoke
    # ------------------------------------------------------------------

    @security_critical
    def revoke(
        self,
        did_string: str,
        reason: str = "unspecified",
        signer: str = "",
    ) -> dict[str, Any]:
        """撤销一个 DID 并联动吊销其治理凭证、失效能力目录。

        返回撤销汇总：DID 记录、本次联动吊销的凭证数量、能力目录状态。
        对已 deactivated 的终态 DID 返回当前记录（不重复变更）。
        """
        did = AgentDID.parse(did_string)
        record = self._did_registry.revoke(did, reason=reason, signer=signer)
        if record is None:
            return {"revoked": False, "reason": f"DID {did_string} 未注册"}
        # 撤销联动（I1）：监听器已吊销该主体凭证，统计本次被吊销的数量。
        credentials_revoked = self._credential_store.revoked_count_for_subject(
            did_string
        )
        card = self._agent_dns.resolve(did)
        return {
            "revoked": True,
            "did": did_string,
            "status": record.status,
            "version": record.version,
            "revocation_entry": record.revocation_entry,
            "credentials_revoked": credentials_revoked,
            "card_active": card is not None,
        }

    # ------------------------------------------------------------------
    # 便利查询
    # ------------------------------------------------------------------

    def is_active(self, did_string: str) -> bool:
        try:
            did = AgentDID.parse(did_string)
        except ValueError:
            return False
        return self._did_registry.is_active(did)

    def list_agents(self, active_only: bool = True) -> list[dict[str, Any]]:
        """列出已注册 agent 的聚合视图。"""
        result: list[dict[str, Any]] = []
        for did in self._did_registry.list_all():
            if active_only and did.status != "active":
                continue
            result.append({
                "did": did.did.did_string,
                "status": did.status,
                "version": did.version,
                "roles": list(did.roles),
            })
        return result

    def summary(self) -> dict[str, Any]:
        return {
            "agents": self._did_registry.agent_count(),
            "cards": self._agent_dns.count(),
            "credentials": self._credential_store.count(),
            "revoked_credentials": self._credential_store.revoked_count(),
        }


__all__ = ["AgentIdentityService"]
