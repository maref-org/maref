"""test_entitlements — macOS 系统扩展 entitlement 生成与验证测试

测试矩阵:
- EntitlementGenerator.generate_esf(): 生成 ESF client 专属 entitlement
- EntitlementGenerator.generate_ne(): 生成 Network Extension 专属 entitlement
- EntitlementGenerator.generate_combined(): 生成组合 entitlement
- EntitlementGenerator.generate_combined_plist_xml(): 生成 XML plist bytes
- EntitlementGenerator.validate_entitlement_dict(): 验证完整性
- EntitlementValidator: 二进制验证 (CI 下返回 None)
"""

from __future__ import annotations

import plistlib

from maref.sentinel.platform.macos.entitlements import (
    COMBINED_ENTITLEMENTS,
    ESF_REQUIRED_ENTITLEMENTS,
    NE_REQUIRED_ENTITLEMENTS,
    EntitlementGenerator,
    EntitlementValidator,
)


class TestConstants:
    """entitlement 常量定义测试"""

    def test_esf_required_has_endpoint_security(self) -> None:
        assert ESF_REQUIRED_ENTITLEMENTS.get("com.apple.developer.endpoint-security.client") is True

    def test_esf_required_has_disable_library_validation(self) -> None:
        assert ESF_REQUIRED_ENTITLEMENTS.get("com.apple.security.cs.disable-library-validation") is True

    def test_ne_required_has_network_extension(self) -> None:
        ne = NE_REQUIRED_ENTITLEMENTS.get("com.apple.developer.networking.networkextension")
        assert isinstance(ne, list)
        assert "packet-tunnel-provider" in ne

    def test_ne_required_has_system_extension_install(self) -> None:
        assert NE_REQUIRED_ENTITLEMENTS.get("com.apple.developer.system-extension.install") is True

    def test_combined_includes_all_esf_keys(self) -> None:
        for key in ESF_REQUIRED_ENTITLEMENTS:
            assert key in COMBINED_ENTITLEMENTS, f"combined missing {key}"

    def test_combined_includes_all_ne_keys(self) -> None:
        for key in NE_REQUIRED_ENTITLEMENTS:
            assert key in COMBINED_ENTITLEMENTS, f"combined missing {key}"

    def test_combined_has_network_client(self) -> None:
        assert COMBINED_ENTITLEMENTS.get("com.apple.security.network.client") is True

    def test_combined_has_file_access(self) -> None:
        assert COMBINED_ENTITLEMENTS.get("com.apple.security.files.user-selected.read-write") is True


class TestEntitlementGenerator:
    """EntitlementGenerator 功能测试"""

    def test_generate_esf_contains_required_keys(self) -> None:
        gen = EntitlementGenerator()
        result = gen.generate_esf()
        for key in ESF_REQUIRED_ENTITLEMENTS:
            assert key in result, f"missing {key}"

    def test_generate_esf_with_extra(self) -> None:
        gen = EntitlementGenerator(extra_entitlements={"com.apple.security.cs.allow-unsigned-executable-memory": True})
        result = gen.generate_esf()
        assert result["com.apple.security.cs.allow-unsigned-executable-memory"] is True

    def test_generate_esf_does_not_include_ne_keys(self) -> None:
        gen = EntitlementGenerator()
        result = gen.generate_esf()
        assert "com.apple.developer.networking.networkextension" not in result
        assert "com.apple.developer.system-extension.install" not in result

    def test_generate_ne_contains_required_keys(self) -> None:
        gen = EntitlementGenerator()
        result = gen.generate_ne()
        for key in NE_REQUIRED_ENTITLEMENTS:
            assert key in result, f"missing {key}"

    def test_generate_ne_does_not_include_esf_keys(self) -> None:
        gen = EntitlementGenerator()
        result = gen.generate_ne()
        assert "com.apple.developer.endpoint-security.client" not in result

    def test_generate_combined_contains_all(self) -> None:
        gen = EntitlementGenerator()
        result = gen.generate_combined()
        for key in COMBINED_ENTITLEMENTS:
            assert key in result, f"missing {key}"

    def test_generate_combined_with_extra(self) -> None:
        gen = EntitlementGenerator(extra_entitlements={"com.apple.security.device.camera": True})
        result = gen.generate_combined()
        assert result["com.apple.security.device.camera"] is True

    def test_generate_combined_plist_xml_is_valid_plist(self) -> None:
        gen = EntitlementGenerator()
        xml_bytes = gen.generate_combined_plist_xml()
        assert isinstance(xml_bytes, bytes)
        assert b"<?xml" in xml_bytes

        # 验证是合法 plist
        parsed = plistlib.loads(xml_bytes)
        for key in COMBINED_ENTITLEMENTS:
            assert key in parsed, f"missing {key} in parsed plist"

    def test_generate_combined_plist_xml_matches_dict(self) -> None:
        gen = EntitlementGenerator()
        xml_bytes = gen.generate_combined_plist_xml()
        parsed = plistlib.loads(xml_bytes)
        combined = gen.generate_combined()
        assert parsed == combined

    def test_generate_combined_plist_xml_extra(self) -> None:
        gen = EntitlementGenerator(extra_entitlements={"com.apple.security.device.camera": True})
        xml_bytes = gen.generate_combined_plist_xml()
        parsed = plistlib.loads(xml_bytes)
        assert parsed["com.apple.security.device.camera"] is True

    def test_generate_esf_preserves_original_constants(self) -> None:
        """generate_esf 不修改原始全局常量"""
        original_keys = set(ESF_REQUIRED_ENTITLEMENTS.keys())
        gen = EntitlementGenerator()
        gen.generate_esf()
        assert set(ESF_REQUIRED_ENTITLEMENTS.keys()) == original_keys

    def test_generate_ne_preserves_original_constants(self) -> None:
        original_keys = set(NE_REQUIRED_ENTITLEMENTS.keys())
        gen = EntitlementGenerator()
        gen.generate_ne()
        assert set(NE_REQUIRED_ENTITLEMENTS.keys()) == original_keys


class TestValidateEntitlementDict:
    """EntitlementGenerator.validate_entitlement_dict 测试"""

    def test_valid_combined_returns_empty(self) -> None:
        gen = EntitlementGenerator()
        combined = gen.generate_combined()
        issues = gen.validate_entitlement_dict(combined)
        assert issues == []

    def test_missing_key_detected(self) -> None:
        issues = EntitlementGenerator.validate_entitlement_dict({})
        assert len(issues) > 0
        assert any("missing required entitlement" in msg for msg in issues)

    def test_missing_endpoint_security_detected(self) -> None:
        d = dict(COMBINED_ENTITLEMENTS)
        del d["com.apple.developer.endpoint-security.client"]
        issues = EntitlementGenerator.validate_entitlement_dict(d)
        assert any("endpoint-security.client" in msg for msg in issues)

    def test_wrong_type_for_list_entitlement_detected(self) -> None:
        d = dict(COMBINED_ENTITLEMENTS)
        d["com.apple.developer.networking.networkextension"] = True  # 应为 list
        issues = EntitlementGenerator.validate_entitlement_dict(d)
        assert any("networking.networkextension" in msg for msg in issues)

    def test_missing_packet_tunnel_detected(self) -> None:
        d = dict(COMBINED_ENTITLEMENTS)
        d["com.apple.developer.networking.networkextension"] = ["content-filter-provider"]
        issues = EntitlementGenerator.validate_entitlement_dict(d)
        assert any("packet-tunnel-provider" in msg for msg in issues)

    def test_wrong_bool_type_detected(self) -> None:
        d = dict(COMBINED_ENTITLEMENTS)
        d["com.apple.developer.endpoint-security.client"] = "yes"  # 应为 bool
        issues = EntitlementGenerator.validate_entitlement_dict(d)
        assert any("endpoint-security.client" in msg for msg in issues)


class TestEntitlementValidator:
    """EntitlementValidator 测试"""

    def test_init_with_hmac_key(self) -> None:
        validator = EntitlementValidator(hmac_key=b"test-key")
        assert validator._hmac_key == b"test-key"  # noqa: SLF001  # 测试需要

    def test_init_without_hmac_key(self) -> None:
        validator = EntitlementValidator()
        assert validator._hmac_key is None  # noqa: SLF001  # 测试需要

    async def test_validate_esf_binary_returns_no_codesign_in_ci(self) -> None:
        """在无 codesign 环境下返回 missing+invalid"""
        validator = EntitlementValidator()
        result = await validator.validate_esf_binary("/nonexistent/binary")
        assert isinstance(result, dict)
        # CI 环境中可能没有 codesign
        assert "valid" in result
        assert "missing" in result
        assert "extra" in result
        assert "raw" in result
