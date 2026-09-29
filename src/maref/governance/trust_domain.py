"""Trust-domain policy — 信任域强制默认化 (NVIDIA 对照矩阵).

P0-3 交付了可选的带外签署后端（``audit_signer``）。本模块把它升级为**策略**：
默认在**生产环境强制**信任域分离，dev/test 不受影响，违规 fail-closed。

强制模式（``TrustDomainMode.ENFORCE``）要求：
1. 审计签署走**外部服务**（``MAREF_AUDIT_SIGNER_URL``），agent 进程不持 HMAC key；
2. 治理运行在**带外进程**（``MAREF_SIDECAR_URL``），而非同进程直连。

默认解析（``resolve_mode``）：
- ``MAREF_TRUST_DOMAIN`` 显式取值优先（enforce/local）；
- 未显式设置时，``MAREF_PRODUCTION`` 为真 → ENFORCE（生产强制），否则 LOCAL。

这实现了"生产默认强制、开发可用"的折中：测试/开发不配置即历史行为，
生产一旦置 ``MAREF_PRODUCTION`` 即强制，且不合规时 :func:`enforce` 直接抛错。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_ENFORCE_VALUES = {"enforce", "strict", "on", "1", "true", "yes"}
_LOCAL_VALUES = {"local", "off", "dev", "0", "false", "no"}


class TrustDomainMode(str, Enum):
    """Trust-domain enforcement mode."""

    LOCAL = "local"
    ENFORCE = "enforce"


class TrustDomainError(RuntimeError):
    """Raised when enforce mode is active but the trust domain is not separated."""


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in _ENFORCE_VALUES


def resolve_mode(environ: Mapping[str, str] | None = None) -> TrustDomainMode:
    """Resolve the trust-domain mode from the environment."""
    env = environ if environ is not None else os.environ
    raw = env.get("MAREF_TRUST_DOMAIN")
    explicit = raw.strip().lower() if raw else ""
    if explicit in _ENFORCE_VALUES:
        return TrustDomainMode.ENFORCE
    if explicit in _LOCAL_VALUES:
        return TrustDomainMode.LOCAL
    return (
        TrustDomainMode.ENFORCE if _truthy(env.get("MAREF_PRODUCTION")) else TrustDomainMode.LOCAL
    )


def _local_key_present(env: Mapping[str, str], *, check_files: bool) -> bool:
    if env.get("MAREF_HMAC_SECRET_KEY", "").strip():
        return True
    if not check_files:
        return False
    try:
        from maref.governance.audit_signer import resolve_local_hmac_key

        return bool(resolve_local_hmac_key())
    except Exception:
        return False


@dataclass
class TrustDomainReport:
    """Assessment of whether the trust domain is separated."""

    mode: TrustDomainMode
    remote_signer_configured: bool
    out_of_process: bool
    local_key_present: bool
    issues: list[str] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        """True when enforce mode has no outstanding issues."""
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "compliant": self.compliant,
            "remote_signer_configured": self.remote_signer_configured,
            "out_of_process": self.out_of_process,
            "local_key_present": self.local_key_present,
            "issues": list(self.issues),
        }


def assess(environ: Mapping[str, str] | None = None) -> TrustDomainReport:
    """Assess trust-domain separation for the current environment."""
    if environ is None:
        env: Mapping[str, str] = os.environ
        check_files = True
    else:
        env = environ
        check_files = False
    mode = resolve_mode(env)
    remote = bool(env.get("MAREF_AUDIT_SIGNER_URL", "").strip())
    out_of_process = bool(env.get("MAREF_SIDECAR_URL", "").strip())
    local_key = _local_key_present(env, check_files=check_files)

    issues: list[str] = []
    if mode == TrustDomainMode.ENFORCE:
        if not remote:
            issues.append("MAREF_AUDIT_SIGNER_URL not set (audit signing not out-of-band)")
        if not out_of_process:
            issues.append("MAREF_SIDECAR_URL not set (governance runs in-process)")
        if local_key:
            issues.append("HMAC key present in agent process")
    return TrustDomainReport(
        mode=mode,
        remote_signer_configured=remote,
        out_of_process=out_of_process,
        local_key_present=local_key,
        issues=issues,
    )


def enforce(environ: Mapping[str, str] | None = None) -> TrustDomainReport:
    """Return the assessment, raising in enforce mode when separation is missing."""
    report = assess(environ)
    if report.mode == TrustDomainMode.ENFORCE and report.issues:
        raise TrustDomainError("trust domain enforcement failed: " + "; ".join(report.issues))
    return report
