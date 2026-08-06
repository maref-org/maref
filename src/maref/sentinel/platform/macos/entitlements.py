"""entitlements — macOS 系统扩展权限管理

为 MAREF 的 ESF client 和 Network Extension 生成/验证 Apple 代码签名 entitlement。

两个系统扩展需要不同的 entitlement:
1. ESF client (maref-esf-client):
   - com.apple.developer.endpoint-security.client → 订阅 ESF 内核事件
   - com.apple.security.cs.disable-library-validation → 加载未签名 bundle

2. Network Extension (maref-network-extension):
   - com.apple.developer.networking.networkextension → [packet-tunnel-provider]
   - com.apple.developer.system-extension.install → 安装系统扩展

用法:
    # 生成组合 plist 内容
    gen = EntitlementGenerator()
    plist_xml = gen.generate_combined()  # → XML string

    # 验证已签名的二进制
    validator = EntitlementValidator()
    status = await validator.validate_esf_binary("/path/to/maref-esf-client")

本模块不读写磁盘,仅生成/验证 entitlement 数据。
实际的 provisioning profile 需在 Apple Developer Portal 创建。
"""

from __future__ import annotations

import plistlib
from typing import Any

# ======================== 常量定义 ========================

# ESF client 必需的 entitlement
ESF_REQUIRED_ENTITLEMENTS: dict[str, Any] = {
    "com.apple.developer.endpoint-security.client": True,
    "com.apple.security.cs.disable-library-validation": True,
    "com.apple.security.cs.allow-jit": True,
    "com.apple.security.network.client": True,
}

# Network Extension 必需的 entitlement
NE_REQUIRED_ENTITLEMENTS: dict[str, Any] = {
    "com.apple.developer.networking.networkextension": [
        "packet-tunnel-provider",
    ],
    "com.apple.developer.system-extension.install": True,
    "com.apple.security.network.client": True,
}

# 组合 (ESF + NE) entitlement
COMBINED_ENTITLEMENTS: dict[str, Any] = {
    # ESF client
    "com.apple.developer.endpoint-security.client": True,
    "com.apple.security.cs.disable-library-validation": True,
    "com.apple.security.cs.allow-jit": True,
    # Network Extension
    "com.apple.developer.networking.networkextension": [
        "packet-tunnel-provider",
    ],
    "com.apple.developer.system-extension.install": True,
    # 通用
    "com.apple.security.network.client": True,
    "com.apple.security.files.user-selected.read-write": True,
}


class EntitlementGeneratorError(Exception):
    """Entitlement 生成错误"""


class EntitlementGenerator:
    """macOS 系统扩展 entitlement 生成器

    生成与 Apple 代码签名工具 (codesign) 兼容的 entitlement plist 内容。
    输出可直接写入 .plist 文件,用于 codesign --entitlements。
    """

    def __init__(self, extra_entitlements: dict[str, Any] | None = None) -> None:
        self._extra = extra_entitlements or {}

    def generate_esf(self) -> dict[str, Any]:
        """生成 ESF client 专用的 entitlement dict

        Returns:
            dict,可直接 plistlib.dumps() 序列化
        """
        result = dict(ESF_REQUIRED_ENTITLEMENTS)
        result.update(self._extra)
        return result

    def generate_ne(self) -> dict[str, Any]:
        """生成 Network Extension 专用的 entitlement dict

        Returns:
            dict,可直接 plistlib.dumps() 序列化
        """
        result = dict(NE_REQUIRED_ENTITLEMENTS)
        result.update(self._extra)
        return result

    def generate_combined(self) -> dict[str, Any]:
        """生成 ESF + NE 组合 entitlement dict

        用于同时部署两个系统扩展的场景。

        Returns:
            dict,可直接 plistlib.dumps() 序列化
        """
        result = dict(COMBINED_ENTITLEMENTS)
        result.update(self._extra)
        return result

    def generate_combined_plist_xml(self) -> bytes:
        """生成组合 entitlement 的 XML plist bytes

        Returns:
            XML bytes,可直接写入 .plist 文件

        Raises:
            EntitlementGeneratorError: 序列化失败
        """
        try:
            return plistlib.dumps(self.generate_combined(), fmt=plistlib.FMT_XML)
        except Exception as exc:
            raise EntitlementGeneratorError(
                f"failed to serialize entitlement plist: {exc}"
            ) from exc

    @staticmethod
    def validate_entitlement_dict(d: dict[str, Any]) -> list[str]:
        """验证 entitlement dict 的完整性

        检查所有必需 key 是否存在且类型正确。

        Args:
            d: 待验证的 entitlement dict

        Returns:
            缺失/无效项的 human-readable 描述列表 (空列表 = 完全合法)
        """
        issues: list[str] = []

        for key, expected in COMBINED_ENTITLEMENTS.items():
            if key not in d:
                issues.append(f"missing required entitlement: {key}")
                continue

            actual = d[key]
            expected_type = type(expected)
            if not isinstance(actual, expected_type):
                issues.append(
                    f"entitlement {key}: expected {expected_type.__name__}, "
                    f"got {type(actual).__name__} ({actual!r})"
                )

            # 对 list 类型,检查是否包含期望值
            if isinstance(expected, list) and isinstance(actual, list):
                for exp_item in expected:
                    if exp_item not in actual:
                        issues.append(
                            f"entitlement {key}: missing expected value {exp_item!r}, "
                            f"got {actual!r}"
                        )

        return issues


class EntitlementValidator:
    """entitlement 运行时验证器

    在 macOS 真机上读取已签名二进制的 entitlement,
    与期望值对比,检测缺失或降级。
    """

    def __init__(self, hmac_key: bytes | None = None) -> None:
        self._hmac_key = hmac_key

    async def validate_esf_binary(self, binary_path: str) -> dict[str, Any]:
        """验证 ESF client 二进制文件的 entitlement (需要 macOS 真机)

        读取二进制 embedded entitlement,与 ESF_REQUIRED_ENTITLEMENTS 对比。

        Args:
            binary_path: ESF client 二进制绝对路径

        Returns:
            {
                "valid": bool,        # 全部必需 entitlement 存在
                "missing": list[str],  # 缺失项
                "extra": list[str],    # 额外项 (非必需但存在)
                "raw": dict,           # 原始 entitlement dict
            }
        """
        raw = await self._read_entitlements(binary_path)
        if raw is None:
            return {
                "valid": False,
                "missing": list(ESF_REQUIRED_ENTITLEMENTS.keys()),
                "extra": [],
                "raw": {},
            }

        missing = []
        extra = []
        for key in ESF_REQUIRED_ENTITLEMENTS:
            if key not in raw:
                missing.append(key)

        for key in raw:
            if key not in ESF_REQUIRED_ENTITLEMENTS:
                extra.append(key)

        return {
            "valid": len(missing) == 0,
            "missing": missing,
            "extra": extra,
            "raw": raw,
        }

    async def _read_entitlements(self, binary_path: str) -> dict[str, Any] | None:
        """读取二进制 embedded entitlement (通过 codesign -d)

        在 CI/无真机环境下返回 None (表示无法验证)。
        """
        import asyncio
        import shutil

        if not shutil.which("codesign"):
            return None  # 无 codesign 工具

        if not shutil.which("plutil"):
            return None  # 无 plutil 工具

        try:
            proc = await asyncio.create_subprocess_exec(
                "codesign",
                "-d",
                "--entitlements",
                "-",
                binary_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode != 0 or not stdout.strip():
                return None

            try:
                return plistlib.loads(stdout)
            except Exception:
                return None
        except (asyncio.TimeoutError, FileNotFoundError, Exception):
            return None
