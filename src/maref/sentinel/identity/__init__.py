"""G1 外部身份指纹 (v0.52.1 M2) — 检测代理在外部平台的多重身份伪造与跨代理共谋。

对位 AISI 欺骗测试发现 ①（伪造多个 GitHub 身份自导自演协同欺骗）与
发现 ④（跨代理公开留言共享账号/遗产）。

模块组成:
- ``account_registry`` — ExternalAccountRegistry 外部账号登记 (声明 vs 实际漂移)
- ``fingerprint`` — IdentityFingerprint 行为指纹提取与相似度比对
- ``sybil_detector`` — SybilDetector 多重身份聚类 (sockpuppet/sybil)
- ``collusion_detector`` — CollusionDetector 自导自演/交叉背书检测
- ``probe`` — IdentityProbe (sentinel Probe 集成)
"""

from __future__ import annotations

from maref.sentinel.identity.account_registry import (
    ExternalAccount,
    ExternalAccountRegistry,
    PlatformType,
)
from maref.sentinel.identity.collusion_detector import (
    CollusionDetector,
    CollusionEvent,
    CollusionKind,
    CollusionReport,
    EndorsementEvent,
    EndorsementKind,
)
from maref.sentinel.identity.fingerprint import (
    FingerprintProfile,
    IdentityFingerprint,
)
from maref.sentinel.identity.probe import IdentityProbe
from maref.sentinel.identity.sybil_detector import (
    SybilCluster,
    SybilDetector,
)

__all__ = [
    "ExternalAccount",
    "ExternalAccountRegistry",
    "PlatformType",
    "FingerprintProfile",
    "IdentityFingerprint",
    "SybilCluster",
    "SybilDetector",
    "CollusionDetector",
    "CollusionEvent",
    "CollusionKind",
    "CollusionReport",
    "EndorsementEvent",
    "EndorsementKind",
    "IdentityProbe",
]
