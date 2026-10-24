"""SM2 Agent 身份证书签发 / 验签（框架 3.0 附件2 二.2 + 正文 3.2.1(a)）。

《人工智能安全治理框架3.0》要求智能体具备可核验的身份标识、支持跨系统互认，
并鼓励采用国密算法。本模块在既有 ``crypto/aia_adapter``（ACPs AIA 国密适配）
的 CAI 结构之上补齐**签发**闭环，并把证书身份与 ``did_registry`` 的 MAREF DID
明确绑定；国家 CA / 统一身份体系对接以 Protocol 预留接口（未联调，见设计文档）。

设计: docs/plans/2026-10-02-maref-framework-3-0-compliance-mapping-plan.md P4
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from maref.crypto.aia_adapter import AgentIdentityCertificate, verify_cai_certificate
from maref.crypto.sm2 import SM2KeyPair, sm2_sign
from maref.crypto.sm3 import sm3_hash
from maref.identity.did_registry import AgentDID

DEFAULT_VALIDITY_DAYS = 365
CERT_FORMAT = "ACPs-CAI/SM2-SM3"
NATIONAL_CA_UNAVAILABLE = "国家 CA 对接为预留接口，尚未与任何外部 CA 联调"

_SIGN_RETRIES = 3


@dataclass(frozen=True)
class VerifyResult:
    """证书验签结果（可布尔化）。"""

    valid: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.valid

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "reasons": list(self.reasons)}


def cai_plaintext(
    agent_id: str,
    public_key: str,
    casp_id: str,
    validity_period: tuple[int, int],
) -> bytes:
    """CAI 签名的规范明文（与 aia_adapter.verify_cai_certificate 严格一致）。"""
    return (f"{agent_id}:{public_key}:{casp_id}:{validity_period[0]}:{validity_period[1]}").encode()


def sm3_fingerprint(public_key: str) -> str:
    """公钥 SM3 指纹（64 hex），用于跨系统身份互认。"""
    return sm3_hash(public_key.encode())


def issue_certificate(
    *,
    agent_id: str,
    subject_public_key: str,
    casp_private_key: str,
    casp_public_key: str,
    casp_id: str,
    validity_days: int = DEFAULT_VALIDITY_DAYS,
    now: int | float | None = None,
) -> AgentIdentityCertificate:
    """由 CASP（签发机构）为 Agent 签发一张 SM2 身份证书（CAI）。

    签名使用 SM3withSM2；因 gmssl 随机 k 极少数产出不可验签签名，签发后自校验，
    失败重签至多 ``_SIGN_RETRIES`` 次，仍失败抛 ``RuntimeError``。
    """
    issued_at = int(now if now is not None else time.time())
    validity_period = (issued_at, issued_at + validity_days * 86400)
    plaintext = cai_plaintext(agent_id, subject_public_key, casp_id, validity_period)

    last_error: Exception | None = None
    for _ in range(_SIGN_RETRIES):
        signature = sm2_sign(casp_private_key, plaintext, public_key=casp_public_key, use_sm3=True)
        candidate = AgentIdentityCertificate(
            agent_id=agent_id,
            public_key=subject_public_key,
            signature=signature,
            casp_id=casp_id,
            validity_period=validity_period,
        )
        if verify_cai_certificate(candidate, casp_public_key):
            return candidate
        last_error = RuntimeError("SM2 签名自校验失败")
    raise last_error or RuntimeError("SM2 签发失败")


def issue_certificate_for_did(
    did_string: str,
    *,
    subject_public_key: str,
    casp_private_key: str,
    casp_public_key: str,
    casp_id: str,
    validity_days: int = DEFAULT_VALIDITY_DAYS,
    now: int | float | None = None,
) -> AgentIdentityCertificate:
    """以 MAREF DID 的 agent_short_id 作为证书主体签发（绑定 did_registry）。"""
    did = AgentDID.parse(did_string)
    return issue_certificate(
        agent_id=did.agent_short_id,
        subject_public_key=subject_public_key,
        casp_private_key=casp_private_key,
        casp_public_key=casp_public_key,
        casp_id=casp_id,
        validity_days=validity_days,
        now=now,
    )


def verify_certificate(
    certificate: AgentIdentityCertificate,
    casp_public_key: str,
    *,
    now: int | float | None = None,
    check_validity: bool = True,
) -> VerifyResult:
    """验证证书：SM3withSM2 签名 + 有效期窗口。

    篡改 agent_id / public_key / casp_id / validity_period 任一字段都会使签名失配。
    """
    reasons: list[str] = []
    if not verify_cai_certificate(certificate, casp_public_key):
        reasons.append("signature-invalid")
    if check_validity:
        ts = int(now if now is not None else time.time())
        start, end = certificate.validity_period
        if ts < start:
            reasons.append("not-yet-valid")
        if ts > end:
            reasons.append("expired")
    return VerifyResult(valid=not reasons, reasons=tuple(reasons))


def verify_did_binding(certificate: AgentIdentityCertificate, did_string: str) -> bool:
    """校验证书主体与给定 MAREF DID 的绑定关系是否一致。"""
    try:
        did = AgentDID.parse(did_string)
    except ValueError:
        return False
    return certificate.agent_id == did.agent_short_id


def export_certificate(certificate: AgentIdentityCertificate) -> dict[str, Any]:
    """导出为国密可互认的证书字典（含 SM3 公钥指纹）。"""
    return {
        "format": CERT_FORMAT,
        "agent_id": certificate.agent_id,
        "public_key": certificate.public_key,
        "casp_id": certificate.casp_id,
        "validity_period": list(certificate.validity_period),
        "signature": certificate.signature,
        "public_key_fingerprint": sm3_fingerprint(certificate.public_key),
    }


def import_certificate(data: dict[str, Any]) -> AgentIdentityCertificate:
    """从导出字典还原证书。"""
    return AgentIdentityCertificate(
        agent_id=data["agent_id"],
        public_key=data["public_key"],
        signature=data["signature"],
        casp_id=data["casp_id"],
        validity_period=(int(data["validity_period"][0]), int(data["validity_period"][1])),
    )


@runtime_checkable
class NationalCAAdapter(Protocol):
    """国家 CA / 统一身份体系对接接口（预留，未联调）。"""

    def issue(
        self,
        *,
        agent_id: str,
        subject_public_key: str,
        validity_days: int = DEFAULT_VALIDITY_DAYS,
    ) -> AgentIdentityCertificate: ...

    def verify(self, certificate: AgentIdentityCertificate) -> VerifyResult: ...


class UnavailableNationalCAAdapter:
    """占位实现：明确标注未与任何外部 CA 联调，调用即抛错（fail-closed）。"""

    def issue(self, **kwargs: Any) -> AgentIdentityCertificate:
        raise NotImplementedError(NATIONAL_CA_UNAVAILABLE)

    def verify(self, certificate: AgentIdentityCertificate) -> VerifyResult:
        raise NotImplementedError(NATIONAL_CA_UNAVAILABLE)


def _selfcheck() -> int:
    keypair = SM2KeyPair.generate()
    cert = issue_certificate(
        agent_id="selfcheck-agent",
        subject_public_key=keypair.public_key,
        casp_private_key=keypair.private_key,
        casp_public_key=keypair.public_key,
        casp_id="selfcheck-casp",
    )
    result = verify_certificate(cert, keypair.public_key)
    print(
        json.dumps(
            {"valid": result.valid, "reasons": list(result.reasons), **export_certificate(cert)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.valid else 1


def main(argv: list[str] | None = None) -> int:
    return _selfcheck()


__all__ = [
    "CERT_FORMAT",
    "DEFAULT_VALIDITY_DAYS",
    "NATIONAL_CA_UNAVAILABLE",
    "NationalCAAdapter",
    "UnavailableNationalCAAdapter",
    "VerifyResult",
    "cai_plaintext",
    "export_certificate",
    "import_certificate",
    "issue_certificate",
    "issue_certificate_for_did",
    "main",
    "sm3_fingerprint",
    "verify_certificate",
    "verify_did_binding",
]


if __name__ == "__main__":
    sys.exit(main())
