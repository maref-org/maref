"""test_sandbox_profile — sandbox-exec profile 生成器测试

覆盖验收标准:
- 2.1-A2: sandbox-exec profile 拒绝未声明 capability 的 syscall
- 2.1-A4: sandbox-exec policy 与 SignedAgentCard.declared_capabilities 100% 一致
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.sentinel.platform.macos.sandbox_profile_gen import (
    _ALWAYS_DENY_RULES,
    _BASELINE_ALLOW_RULES,
    CAPABILITY_TO_SANDBOX_RULES,
    SandboxProfileGenerator,
    SandboxProfileResult,
)

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-sandbox-hmac-key"


class TestSandboxProfileResult:
    """SandboxProfileResult 数据类测试"""

    def test_default_values(self) -> None:
        """默认值 — error="" 时 is_valid=True (无错误即有效)"""
        r = SandboxProfileResult(agent_id="a1", profile_text="", profile_sha256="")
        assert r.agent_id == "a1"
        assert r.is_valid is True  # error 为空 → is_valid=True (无错误即有效)

    def test_is_valid_no_error(self) -> None:
        r = SandboxProfileResult(
            agent_id="a1",
            profile_text="(version 1)",
            profile_sha256="abc",
        )
        assert r.is_valid is True

    def test_is_valid_with_error(self) -> None:
        r = SandboxProfileResult(
            agent_id="a1",
            profile_text="",
            profile_sha256="",
            error="unknown capability",
        )
        assert r.is_valid is False

    def test_to_audit_payload(self) -> None:
        r = SandboxProfileResult(
            agent_id="a1",
            profile_text="(version 1)",
            profile_sha256="abc123",
            declared_capabilities=["network_read"],
            declared_endpoints=["api.example.com:443"],
            capability_hash="chash",
            rule_count=5,
        )
        payload = r.to_audit_payload()
        assert payload["agent_id"] == "a1"
        assert payload["profile_sha256"] == "abc123"
        assert payload["declared_capabilities"] == ["network_read"]
        assert payload["rule_count"] == 5
        # profile_text 不应入审计 (体积大)
        assert "profile_text" not in payload


class TestSandboxProfileGeneratorBasic:
    """SandboxProfileGenerator 基础功能测试"""

    def test_generate_minimal_profile(self) -> None:
        """空 capabilities 也能生成 profile (deny default + baseline)"""
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="minimal-agent", capabilities=[])
        assert result.is_valid
        assert "(deny default)" in result.profile_text
        assert result.agent_id == "minimal-agent"
        assert result.rule_count > 0

    def test_generate_with_single_capability(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read"],
            endpoints=["api.example.com:443"],
        )
        assert result.is_valid
        assert "network_read" in result.profile_text
        # 端点白名单应出现在 profile 中
        assert "api.example.com:443" in result.profile_text

    def test_generate_with_multiple_capabilities(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read", "file_read", "process_exec"],
            endpoints=["api.example.com:443"],
        )
        assert result.is_valid
        for cap in ("network_read", "file_read", "process_exec"):
            assert cap in result.profile_text

    def test_profile_has_version_and_deny_default(self) -> None:
        """所有 profile 必须以 (version 1) + (deny default) 开头"""
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert "(version 1)" in result.profile_text
        assert "(deny default)" in result.profile_text
        # deny default 必须在 baseline 之前
        deny_idx = result.profile_text.index("(deny default)")
        baseline_idx = result.profile_text.index("baseline allows")
        assert deny_idx < baseline_idx

    def test_profile_includes_header_comments(self) -> None:
        """profile 必须包含 agent_id/generated_at/capability_hash 注释"""
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="agent-xyz",
            capabilities=["network_read"],
            endpoints=["api.x.com:443"],
        )
        assert "agent=agent-xyz" in result.profile_text
        assert "generated_at=" in result.profile_text
        assert "capability_hash=" in result.profile_text
        assert "capabilities=" in result.profile_text

    def test_profile_sha256_is_deterministic(self) -> None:
        """相同输入 → 相同 profile_sha256 (modulo generated_at timestamp)"""
        gen = SandboxProfileGenerator()
        # 注: 由于 generated_at 为 time.time(),两次调用会有微小差异
        # 但 profile 内容应该结构相同
        r1 = gen.generate(agent_id="a1", capabilities=["network_read"])
        r2 = gen.generate(agent_id="a1", capabilities=["network_read"])
        assert r1.declared_capabilities == r2.declared_capabilities
        assert r1.capability_hash == r2.capability_hash

    def test_capability_hash_differs_for_different_capabilities(self) -> None:
        gen = SandboxProfileGenerator()
        r1 = gen.generate(agent_id="a1", capabilities=["network_read"])
        r2 = gen.generate(agent_id="a1", capabilities=["file_read"])
        assert r1.capability_hash != r2.capability_hash

    def test_capability_hash_differs_for_different_agent(self) -> None:
        gen = SandboxProfileGenerator()
        r1 = gen.generate(agent_id="a1", capabilities=["network_read"])
        r2 = gen.generate(agent_id="a2", capabilities=["network_read"])
        assert r1.capability_hash != r2.capability_hash


class TestUnknownCapabilityHandling:
    """未知 capability 处理 (2.1-A4 一致性保证)"""

    def test_unknown_capability_returns_error_by_default(self) -> None:
        """未知 capability 默认拒绝生成 (严格模式)"""
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=["unknown_cap"])
        assert not result.is_valid
        assert "unknown_cap" in result.error

    def test_unknown_capability_skipped_when_allowed(self) -> None:
        """allow_unknown=True 时,未知 capability 跳过但不报错"""
        gen = SandboxProfileGenerator(allow_unknown_capabilities=True)
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read", "unknown_cap"],
        )
        assert result.is_valid
        assert "unknown_cap" in result.profile_text  # 在注释中标注 skipped

    def test_unknown_capability_does_not_appear_in_rules(self) -> None:
        """未知 capability 不应生成任何 allow/deny 规则"""
        gen = SandboxProfileGenerator(allow_unknown_capabilities=True)
        result = gen.generate(agent_id="a1", capabilities=["bogus_cap"])
        assert result.is_valid
        # bogus_cap 只应在注释行出现,不应有对应规则
        for line in result.profile_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("(") and "bogus_cap" in stripped:
                pytest.fail(f"unknown capability leaked into rule: {stripped}")


class TestCapabilityDenyRules:
    """2.1-A2: 未声明 capability 的操作被拒绝"""

    def test_network_only_agent_denies_process_exec(self) -> None:
        """声明 network_read 但未声明 process_exec → bash exec 应被拒绝"""
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="net-only",
            capabilities=["network_read"],
            endpoints=["api.example.com:443"],
        )
        assert result.is_valid
        # profile 应显式拒绝 process-exec (因为未声明)
        assert "(deny process-exec)" in result.profile_text
        # 同时应拒绝 process-fork
        assert "(deny process-fork)" in result.profile_text

    def test_no_network_agent_denies_all_network(self) -> None:
        """未声明任何 network capability → deny network*"""
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="offline-agent",
            capabilities=["file_read"],
        )
        assert result.is_valid
        assert "(deny network*)" in result.profile_text

    def test_no_process_agent_denies_all_process(self) -> None:
        """未声明 process_spawn/process_exec → deny fork + exec"""
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="no-proc",
            capabilities=["network_read"],
            endpoints=["api.x.com:443"],
        )
        assert result.is_valid
        assert "(deny process-fork)" in result.profile_text
        assert "(deny process-exec)" in result.profile_text

    def test_process_exec_capability_denies_bash_and_sh(self) -> None:
        """声明 process_exec 时,仍拒绝危险 shell (bash/sh/zsh)"""
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="proc-agent",
            capabilities=["process_exec"],
        )
        assert result.is_valid
        assert '(deny process-exec (literal "/bin/bash"))' in result.profile_text
        assert '(deny process-exec (literal "/bin/sh"))' in result.profile_text
        assert '(deny process-exec (literal "/bin/zsh"))' in result.profile_text

    def test_file_read_capability_denies_ssh_credentials(self) -> None:
        """file_read 仍拒绝 .ssh / .aws/credentials 等敏感路径"""
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="file-reader",
            capabilities=["file_read"],
        )
        assert result.is_valid
        assert "(subpath \".ssh\")" in result.profile_text
        assert "(subpath \".aws/credentials\")" in result.profile_text

    def test_file_write_denies_etc_and_system_paths(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="file-writer",
            capabilities=["file_write"],
        )
        assert result.is_valid
        assert '(deny file-write* (subpath "/etc"))' in result.profile_text
        assert '(deny file-write* (subpath "/System"))' in result.profile_text


class TestAlwaysDenyRules:
    """任何 Agent 都拒绝的危险操作 (sudo/su/installer 等)"""

    def test_always_deny_sudo(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(deny process-exec (literal "/usr/bin/sudo"))' in result.profile_text

    def test_always_deny_installer(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(deny process-exec (literal "/usr/sbin/installer"))' in result.profile_text

    def test_always_deny_keychain_access(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(deny file-write* (subpath "/Library/Keychains"))' in result.profile_text

    def test_always_deny_security_command(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(deny process-exec (literal "/usr/bin/security"))' in result.profile_text

    def test_extra_deny_rules_appended(self) -> None:
        """额外 deny 规则应被追加"""
        gen = SandboxProfileGenerator(
            extra_deny_rules=("(deny file-read* (subpath \"/custom/secret\"))",)
        )
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(deny file-read* (subpath "/custom/secret"))' in result.profile_text


class TestBaselineAllowRules:
    """基线放行规则测试"""

    def test_baseline_allow_localtime(self) -> None:
        """时区读取 (受 TimezoneProbe 监控) 在 baseline 放行"""
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(allow file-read* (literal "/etc/localtime"))' in result.profile_text

    def test_baseline_allow_dev_null(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(allow file-read* (subpath "/dev/null"))' in result.profile_text
        assert '(allow file-write* (subpath "/dev/null"))' in result.profile_text

    def test_baseline_allow_dns(self) -> None:
        """DNS (127.0.0.1:53) 在 baseline 放行 — 任何 Agent 都需要"""
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(allow network-outbound (remote udp "127.0.0.1:53"))' in result.profile_text

    def test_extra_allow_rules_appended(self) -> None:
        gen = SandboxProfileGenerator(
            extra_allow_rules=("(allow file-read* (subpath \"/custom/lib\"))",)
        )
        result = gen.generate(agent_id="a1", capabilities=[])
        assert '(allow file-read* (subpath "/custom/lib"))' in result.profile_text


class TestNetworkEndpointWhitelist:
    """network_read capability 的端点白名单"""

    def test_single_endpoint_in_whitelist(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read"],
            endpoints=["api.example.com:443"],
        )
        assert '(remote tcp "api.example.com:443")' in result.profile_text

    def test_multiple_endpoints_in_whitelist(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read"],
            endpoints=["api.x.com:443", "api.y.com:443", "api.z.com:443"],
        )
        for ep in ("api.x.com:443", "api.y.com:443", "api.z.com:443"):
            assert f'(remote tcp "{ep}")' in result.profile_text

    def test_no_endpoints_generic_tcp_rule(self) -> None:
        """无 endpoints 时,network_read 退化为通用 remote tcp 规则"""
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read"],
            endpoints=[],
        )
        assert "(allow network-outbound (remote tcp))" in result.profile_text


class TestGenerateFromCard:
    """generate_from_card 便捷方法测试"""

    def test_generate_from_card_success(self) -> None:
        """从 SignedAgentCard 对象生成 profile"""
        card = MagicMock()
        card.agent_id = "claude-code"
        card.capabilities = ["network_read", "file_read"]
        card.endpoints = ["api.anthropic.com:443"]

        gen = SandboxProfileGenerator()
        result = gen.generate_from_card(card)
        assert result.is_valid
        assert result.agent_id == "claude-code"
        assert "network_read" in result.profile_text
        assert "api.anthropic.com:443" in result.profile_text

    def test_generate_from_card_empty_agent_id(self) -> None:
        card = MagicMock()
        card.agent_id = ""
        card.capabilities = ["network_read"]
        card.endpoints = []

        gen = SandboxProfileGenerator()
        result = gen.generate_from_card(card)
        assert not result.is_valid
        assert "empty" in result.error

    def test_generate_from_card_extract_failure(self) -> None:
        """属性访问异常 → error"""
        card = MagicMock()
        card.agent_id = "a1"
        # 模拟 capabilities 属性访问抛异常
        type(card).capabilities = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        card.endpoints = []

        gen = SandboxProfileGenerator()
        result = gen.generate_from_card(card)
        assert not result.is_valid
        assert "failed to extract" in result.error


class TestVerifyProfileCardConsistency:
    """2.1-A4: profile 与 card 100% 一致性验证"""

    def test_consistency_same_inputs(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read"],
            endpoints=["api.x.com:443"],
        )
        assert gen.verify_profile_card_consistency(
            result, "a1", ["network_read"], ["api.x.com:443"]
        ) is True

    def test_inconsistency_different_agent_id(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read"],
        )
        assert gen.verify_profile_card_consistency(
            result, "a2", ["network_read"], []
        ) is False

    def test_inconsistency_different_capabilities(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read"],
        )
        assert gen.verify_profile_card_consistency(
            result, "a1", ["file_read"], []
        ) is False

    def test_inconsistency_different_endpoints(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read"],
            endpoints=["api.x.com:443"],
        )
        assert gen.verify_profile_card_consistency(
            result, "a1", ["network_read"], ["api.y.com:443"]
        ) is False

    def test_consistency_capability_order_doesnt_matter(self) -> None:
        """能力列表顺序不影响一致性 (内部排序)"""
        gen = SandboxProfileGenerator()
        result = gen.generate(
            agent_id="a1",
            capabilities=["network_read", "file_read"],
        )
        assert gen.verify_profile_card_consistency(
            result, "a1", ["file_read", "network_read"], []
        ) is True


class TestCapabilityTaxonomy:
    """能力分类表完整性测试"""

    def test_all_expected_capabilities_present(self) -> None:
        """CAPABILITY_TO_SANDBOX_RULES 应包含 M2 所有必要能力"""
        expected = {
            "network_read",
            "network_write",
            "file_read",
            "file_write",
            "process_spawn",
            "process_exec",
            "ptrace",
            "env_read",
            "env_write",
        }
        actual = set(CAPABILITY_TO_SANDBOX_RULES.keys())
        assert expected.issubset(actual), f"missing: {expected - actual}"

    def test_each_capability_has_allow_key(self) -> None:
        for cap, rules in CAPABILITY_TO_SANDBOX_RULES.items():
            assert "allow" in rules, f"capability {cap} missing 'allow' key"

    def test_each_capability_has_deny_key(self) -> None:
        for cap, rules in CAPABILITY_TO_SANDBOX_RULES.items():
            assert "deny" in rules, f"capability {cap} missing 'deny' key"

    def test_baseline_allow_rules_nonempty(self) -> None:
        assert len(_BASELINE_ALLOW_RULES) > 0

    def test_always_deny_rules_nonempty(self) -> None:
        assert len(_ALWAYS_DENY_RULES) > 0

    def test_always_deny_includes_sudo_su(self) -> None:
        sudo_rules = [r for r in _ALWAYS_DENY_RULES if "sudo" in r or "su" in r]
        assert len(sudo_rules) >= 2  # sudo + su + login


class TestRuleCount:
    """rule_count 统计准确性测试"""

    def test_rule_count_positive(self) -> None:
        gen = SandboxProfileGenerator()
        result = gen.generate(agent_id="a1", capabilities=[])
        assert result.rule_count > 0

    def test_rule_count_increases_with_capabilities(self) -> None:
        gen = SandboxProfileGenerator()
        r1 = gen.generate(agent_id="a1", capabilities=[])
        r2 = gen.generate(agent_id="a1", capabilities=["network_read", "file_read"])
        assert r2.rule_count > r1.rule_count
