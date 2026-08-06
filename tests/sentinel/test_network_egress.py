"""
NetworkEgressProbe 测试 — 覆盖验收标准 1.2-A1/A2/A3 + HMAC + 生命周期

测试矩阵:
- 1.2-A1: 1x1 透明像素 URL 检出率 ≥ 90%, 误报率 ≤ 5%
- 1.2-A2: 日期分隔符 / 替换 - 的隐写检出率 ≥ 85%
- 1.2-A3: 未在 declared_endpoints 中的外联域名检出率 100%
- HMAC 签名完整性
- FlowRecord 属性 (host/path/content_type)
- Probe 生命周期 (start/stop 幂等)
- submit_flow + poll 流转
- 背压 (队列满)
- health_check
"""

from __future__ import annotations

import asyncio

import pytest

from maref.sentinel.event import AttackType, Severity, verify_event_hash
from maref.sentinel.probes.base import ProbeConfig
from maref.sentinel.probes.network_egress_probe import FlowRecord, NetworkEgressProbe

# 真实的 1x1 透明 GIF89a bytes (43 字节,标准 1x1 透明 GIF)
_1x1_GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
# 真实的 1x1 PNG bytes (67 字节)
_1x1_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

HMAC_KEY = b"test-hmac-key-for-network-egress-probe"


def _make_probe(
    declared_endpoints: tuple[str, ...] = (),
) -> NetworkEgressProbe:
    """构造带 HMAC key 的 NetworkEgressProbe"""
    return NetworkEgressProbe(
        config=ProbeConfig(hmac_key=HMAC_KEY, poll_interval=0.01),
        declared_endpoints=declared_endpoints,
    )


def _make_flow(
    url: str = "https://example.com/path",
    method: str = "GET",
    status_code: int = 200,
    request_headers: dict[str, str] | None = None,
    response_headers: dict[str, str] | None = None,
    response_body: bytes = b"",
    request_body: bytes = b"",
    agent_id: str = "",
) -> FlowRecord:
    """构造 FlowRecord 测试用例"""
    return FlowRecord(
        timestamp=1700000000.0,
        method=method,
        url=url,
        request_headers=request_headers or {},
        request_body=request_body,
        status_code=status_code,
        response_headers=response_headers or {},
        response_body=response_body,
        client_ip="127.0.0.1",
        agent_id=agent_id,
    )


# ==================== FlowRecord 属性测试 ====================


class TestFlowRecord:
    """FlowRecord dataclass 属性测试"""

    def test_host_extraction(self) -> None:
        flow = _make_flow(url="https://api.anthropic.com/v1/messages")
        assert flow.host == "api.anthropic.com"

    def test_host_extraction_uppercase_normalized(self) -> None:
        flow = _make_flow(url="https://API.Anthropic.COM/v1")
        assert flow.host == "api.anthropic.com"

    def test_path_extraction(self) -> None:
        flow = _make_flow(url="https://example.com/v1/messages?x=1")
        assert flow.path == "/v1/messages"

    def test_path_default_when_empty(self) -> None:
        flow = _make_flow(url="https://example.com")
        assert flow.path == "/"

    def test_content_type_lowercase(self) -> None:
        flow = _make_flow(response_headers={"content-type": "IMAGE/GIF"})
        assert flow.content_type == "image/gif"

    def test_content_type_missing(self) -> None:
        flow = _make_flow(response_headers={})
        assert flow.content_type == ""

    def test_flow_record_is_frozen(self) -> None:
        flow = _make_flow()
        with pytest.raises(Exception):
            flow.url = "https://other.com"  # type: ignore[misc]


# ==================== 1.2-A1: 像素追踪检出率 ≥ 90% ====================


class TestPixelTrackingDetection:
    """1.2-A1: NetworkEgressProbe 对 1x1 透明像素 URL 检出率 ≥ 90%, 误报率 ≤ 5%"""

    @pytest.fixture
    def probe(self) -> NetworkEgressProbe:
        return _make_probe()

    @pytest.mark.asyncio
    async def test_pixel_url_keyword_detected(
        self, probe: NetworkEgressProbe
    ) -> None:
        """URL 含 pixel/tracking 关键词 → 检出"""
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://tracking.example.com/pixel.gif",
                response_headers={"content-type": "image/gif"},
                response_body=_1x1_GIF_BYTES,
            )
        )
        events = await probe.poll()
        await probe.stop()

        pixel_events = [e for e in events if e.attack_type == AttackType.PIXEL_TRACKING]
        assert len(pixel_events) >= 1
        ev = pixel_events[0]
        assert ev.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)
        assert "url_keyword" in ev.evidence["signals"][0]

    @pytest.mark.asyncio
    async def test_1x1_gif_magic_bytes_detected(
        self, probe: NetworkEgressProbe
    ) -> None:
        """响应体为 1x1 GIF magic bytes → 检出"""
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://example.com/img",
                response_headers={"content-type": "image/gif"},
                response_body=_1x1_GIF_BYTES,
            )
        )
        events = await probe.poll()
        await probe.stop()

        pixel_events = [e for e in events if e.attack_type == AttackType.PIXEL_TRACKING]
        assert len(pixel_events) == 1
        signals = pixel_events[0].evidence["signals"]
        assert any("body:1x1_gif_magic" in s for s in signals)

    @pytest.mark.asyncio
    async def test_1x1_png_magic_bytes_detected(
        self, probe: NetworkEgressProbe
    ) -> None:
        """响应体为 1x1 PNG magic bytes → 检出"""
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://example.com/img",
                response_headers={"content-type": "image/png"},
                response_body=_1x1_PNG_BYTES,
            )
        )
        events = await probe.poll()
        await probe.stop()

        pixel_events = [e for e in events if e.attack_type == AttackType.PIXEL_TRACKING]
        assert len(pixel_events) == 1
        signals = pixel_events[0].evidence["signals"]
        assert any("body:1x1_png_magic" in s for s in signals)

    @pytest.mark.asyncio
    async def test_small_image_with_tracking_header(
        self, probe: NetworkEgressProbe
    ) -> None:
        """小体积图片 + X-Tracker 头 → 检出"""
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://example.com/notify",
                response_headers={
                    "content-type": "image/gif",
                    "X-Tracker-Id": "abc123",
                },
                response_body=b"GIF89a small fake body",
            )
        )
        events = await probe.poll()
        await probe.stop()

        pixel_events = [e for e in events if e.attack_type == AttackType.PIXEL_TRACKING]
        assert len(pixel_events) == 1

    @pytest.mark.asyncio
    async def test_pixel_detection_rate_above_90_percent(
        self, probe: NetworkEgressProbe
    ) -> None:
        """1.2-A1: 10 个像素追踪变体,检出率 ≥ 90% (≥9 个)"""
        pixel_flows = [
            # 1. URL 关键词: pixel
            _make_flow(url="https://t.com/pixel", response_body=b""),
            # 2. URL 关键词: beacon
            _make_flow(url="https://t.com/beacon.gif", response_body=b""),
            # 3. URL 关键词: tracking
            _make_flow(url="https://t.com/tracking", response_body=b""),
            # 4. URL 关键词: 1x1
            _make_flow(url="https://t.com/1x1.gif", response_body=b""),
            # 5. URL 关键词: __utm.gif
            _make_flow(url="https://t.com/__utm.gif", response_body=b""),
            # 6. 1x1 GIF magic bytes
            _make_flow(
                url="https://t.com/img",
                response_headers={"content-type": "image/gif"},
                response_body=_1x1_GIF_BYTES,
            ),
            # 7. 1x1 PNG magic bytes
            _make_flow(
                url="https://t.com/img2",
                response_headers={"content-type": "image/png"},
                response_body=_1x1_PNG_BYTES,
            ),
            # 8. 小体积 image/gif
            _make_flow(
                url="https://t.com/small",
                response_headers={"content-type": "image/gif"},
                response_body=b"x" * 50,
            ),
            # 9. X-Pixel 头
            _make_flow(
                url="https://t.com/track",
                response_headers={"X-Pixel-Id": "abc"},
                response_body=b"",
            ),
            # 10. URL 关键词: ping
            _make_flow(url="https://t.com/ping", response_body=b""),
        ]

        await probe.start()
        for flow in pixel_flows:
            await probe.submit_flow(flow)
        events = await probe.poll()
        await probe.stop()

        detected = sum(
            1 for e in events if e.attack_type == AttackType.PIXEL_TRACKING
        )
        # 检出率 ≥ 90% (10 个中至少 9 个)
        assert detected >= 9, f"Pixel tracking detection rate: {detected}/10 < 9"

    @pytest.mark.asyncio
    async def test_pixel_false_positive_rate_below_5_percent(
        self, probe: NetworkEgressProbe
    ) -> None:
        """1.2-A1: 误报率 ≤ 5% — 10 个正常 flow,误报 ≤ 0 (5% of 10 = 0.5 → 0)"""
        benign_flows = [
            _make_flow(
                url="https://api.anthropic.com/v1/messages",
                response_headers={"content-type": "application/json"},
                response_body=b'{"id":"msg_abc","content":"hello"}',
            ),
            _make_flow(
                url="https://api.openai.com/v1/chat/completions",
                response_headers={"content-type": "application/json"},
                response_body=b'{"choices":[]}',
            ),
            _make_flow(
                url="https://files.example.com/document.pdf",
                response_headers={"content-type": "application/pdf"},
                response_body=b"%PDF-1.4 fake pdf content",
            ),
            _make_flow(
                url="https://cdn.example.com/app.js",
                response_headers={"content-type": "application/javascript"},
                response_body=b"console.log('hello');",
            ),
            _make_flow(
                url="https://example.com/index.html",
                response_headers={"content-type": "text/html"},
                response_body=b"<html><body>Hello</body></html>",
            ),
            _make_flow(
                url="https://registry.npmjs.org/maref",
                response_headers={"content-type": "application/json"},
                response_body=b'{"name":"maref"}',
            ),
            _make_flow(
                url="https://api.github.com/repos/maref-org/maref",
                response_headers={"content-type": "application/json"},
                response_body=b'{"id":123}',
            ),
            _make_flow(
                url="https://pypi.org/simple/maref/",
                response_headers={"content-type": "text/html"},
                response_body=b"<html>maref package</html>",
            ),
            _make_flow(
                url="https://docs.example.com/guide",
                response_headers={"content-type": "text/html"},
                response_body=b"<html>docs</html>",
            ),
            _make_flow(
                url="https://example.com/api/data",
                response_headers={"content-type": "application/json"},
                response_body=b'{"data":[1,2,3]}',
            ),
        ]

        await probe.start()
        for flow in benign_flows:
            await probe.submit_flow(flow)
        events = await probe.poll()
        await probe.stop()

        false_positives = sum(
            1 for e in events if e.attack_type == AttackType.PIXEL_TRACKING
        )
        # 误报率 ≤ 5% (10 个中误报 ≤ 0,因 5% of 10 = 0.5)
        assert false_positives == 0, (
            f"False positive rate: {false_positives}/10 > 5%"
        )


# ==================== 1.2-A2: 日期分隔符隐写检出率 ≥ 85% ====================


class TestDateSteganographyDetection:
    """1.2-A2: NetworkEgressProbe 对日期分隔符 / 替换 - 的隐写检出率 ≥ 85%"""

    @pytest.mark.asyncio
    async def test_slash_date_in_body_detected(self) -> None:
        """响应体含 YYYY/MM/DD → 检出"""
        probe = _make_probe()
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://example.com/api",
                response_body=b'{"date":"2024/01/15","user":"abc"}',
            )
        )
        events = await probe.poll()
        await probe.stop()

        stego_events = [
            e for e in events if e.attack_type == AttackType.STEGANOGRAPHY
        ]
        assert len(stego_events) == 1
        assert stego_events[0].severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_mixed_separators_critical(self) -> None:
        """同一响应中 / 和 - 日期共存 → CRITICAL (强隐写信号)"""
        probe = _make_probe()
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://example.com/api",
                response_body=b'dates: 2024/01/15 and 2024-02-20 mixed',
            )
        )
        events = await probe.poll()
        await probe.stop()

        stego_events = [
            e for e in events if e.attack_type == AttackType.STEGANOGRAPHY
        ]
        assert len(stego_events) == 1
        assert stego_events[0].severity == Severity.CRITICAL
        signals = stego_events[0].evidence["signals"]
        assert any("mixed_separators" in s for s in signals)

    @pytest.mark.asyncio
    async def test_slash_date_in_header_critical(self) -> None:
        """Date 头含 YYYY/MM/DD → CRITICAL (HTTP 标准格式不含 /)"""
        probe = _make_probe()
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://example.com/api",
                response_headers={"date": "2024/01/15 12:00:00"},
                response_body=b"ok",
            )
        )
        events = await probe.poll()
        await probe.stop()

        stego_events = [
            e for e in events if e.attack_type == AttackType.STEGANOGRAPHY
        ]
        assert len(stego_events) == 1
        assert stego_events[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_slash_datetime_in_body_detected(self) -> None:
        """响应体含 YYYY/MM/DD HH:MM:SS → 检出"""
        probe = _make_probe()
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://example.com/api",
                response_body=b'timestamp: 2024/01/15 12:30:45',
            )
        )
        events = await probe.poll()
        await probe.stop()

        stego_events = [
            e for e in events if e.attack_type == AttackType.STEGANOGRAPHY
        ]
        assert len(stego_events) >= 1

    @pytest.mark.asyncio
    async def test_stego_detection_rate_above_85_percent(self) -> None:
        """1.2-A2: 7 个隐写变体,检出率 ≥ 85% (≥6 个)"""
        stego_flows = [
            # 1. body 含 YYYY/MM/DD
            _make_flow(response_body=b'{"date":"2024/01/15"}'),
            # 2. body 含 YYYY/MM/DD HH:MM:SS
            _make_flow(response_body=b'ts: 2024/03/20 14:30:00'),
            # 3. body 混合 / 和 -
            _make_flow(response_body=b'2024/01/15 vs 2024-02-20'),
            # 4. Date 头含 /
            _make_flow(
                response_headers={"date": "2024/05/10 08:00:00"},
                response_body=b"ok",
            ),
            # 5. Last-Modified 头含 /
            _make_flow(
                response_headers={"last-modified": "2024/06/01 12:00:00"},
                response_body=b"ok",
            ),
            # 6. body 多个 / 日期
            _make_flow(response_body=b'log: 2024/01/01 2024/02/01 2024/03/01'),
            # 7. Expires 头含 /
            _make_flow(
                response_headers={"expires": "2024/12/31 23:59:59"},
                response_body=b"ok",
            ),
        ]

        probe = _make_probe()
        await probe.start()
        for flow in stego_flows:
            await probe.submit_flow(flow)
        events = await probe.poll()
        await probe.stop()

        detected = sum(
            1 for e in events if e.attack_type == AttackType.STEGANOGRAPHY
        )
        # 检出率 ≥ 85% (7 个中至少 6 个)
        assert detected >= 6, f"Stego detection rate: {detected}/7 < 85%"

    @pytest.mark.asyncio
    async def test_normal_iso_date_not_flagged(self) -> None:
        """正常 ISO 日期 (YYYY-MM-DD) 不应被标为隐写"""
        probe = _make_probe()
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://example.com/api",
                response_headers={"date": "Mon, 15 Jan 2024 12:00:00 GMT"},
                response_body=b'{"created_at":"2024-01-15T12:00:00Z"}',
            )
        )
        events = await probe.poll()
        await probe.stop()

        stego_events = [
            e for e in events if e.attack_type == AttackType.STEGANOGRAPHY
        ]
        assert len(stego_events) == 0


# ==================== 1.2-A3: 未声明外联检出率 100% ====================


class TestUndeclaredEgressDetection:
    """1.2-A3: NetworkEgressProbe 对未在 declared_endpoints 中的外联域名检出率 100%"""

    @pytest.mark.asyncio
    async def test_undeclared_host_detected(self) -> None:
        """未声明域名 → CRITICAL"""
        probe = _make_probe(
            declared_endpoints=("api.anthropic.com", "api.openai.com")
        )
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://evil.example.com/exfil",
                agent_id="claude-code",
            )
        )
        events = await probe.poll()
        await probe.stop()

        egress_events = [
            e for e in events if e.attack_type == AttackType.PRIVILEGE_ABUSE
        ]
        assert len(egress_events) == 1
        assert egress_events[0].severity == Severity.CRITICAL
        assert egress_events[0].evidence["host"] == "evil.example.com"
        assert egress_events[0].evidence["detection"] == "undeclared_egress"

    @pytest.mark.asyncio
    async def test_declared_host_not_flagged(self) -> None:
        """已声明域名 → 不告警"""
        probe = _make_probe(
            declared_endpoints=("api.anthropic.com",)
        )
        await probe.start()
        await probe.submit_flow(
            _make_flow(url="https://api.anthropic.com/v1/messages")
        )
        events = await probe.poll()
        await probe.stop()

        egress_events = [
            e for e in events if e.attack_type == AttackType.PRIVILEGE_ABUSE
        ]
        assert len(egress_events) == 0

    @pytest.mark.asyncio
    async def test_subdomain_of_declared_not_flagged(self) -> None:
        """已声明域名的子域名 → 不告警 (后缀匹配)"""
        probe = _make_probe(
            declared_endpoints=("anthropic.com",)
        )
        await probe.start()
        await probe.submit_flow(
            _make_flow(url="https://api.anthropic.com/v1/messages")
        )
        events = await probe.poll()
        await probe.stop()

        egress_events = [
            e for e in events if e.attack_type == AttackType.PRIVILEGE_ABUSE
        ]
        assert len(egress_events) == 0

    @pytest.mark.asyncio
    async def test_undeclared_egress_detection_rate_100_percent(self) -> None:
        """1.2-A3: 5 个未声明外联 → 全部检出 (100%)"""
        undeclared_flows = [
            _make_flow(url="https://evil1.com/exfil", agent_id="a1"),
            _make_flow(url="https://evil2.com/data", agent_id="a2"),
            _make_flow(url="https://evil3.com/pixel", agent_id="a3"),
            _make_flow(url="https://evil4.com/beacon", agent_id="a4"),
            _make_flow(url="https://evil5.com/track", agent_id="a5"),
        ]

        probe = _make_probe(
            declared_endpoints=("api.anthropic.com", "api.openai.com")
        )
        await probe.start()
        for flow in undeclared_flows:
            await probe.submit_flow(flow)
        events = await probe.poll()
        await probe.stop()

        egress_events = [
            e
            for e in events
            if e.attack_type == AttackType.PRIVILEGE_ABUSE
            and e.evidence.get("detection") == "undeclared_egress"
        ]
        assert len(egress_events) == 5, (
            f"Undeclared egress detection: {len(egress_events)}/5 != 100%"
        )

    @pytest.mark.asyncio
    async def test_no_declared_endpoints_skips_detection(self) -> None:
        """declared_endpoints 为空 → 不检测 (避免误报, M4 接入 SignedAgentCardStore)"""
        probe = _make_probe(declared_endpoints=())
        await probe.start()
        await probe.submit_flow(
            _make_flow(url="https://any-host.com/anywhere")
        )
        events = await probe.poll()
        await probe.stop()

        egress_events = [
            e
            for e in events
            if e.attack_type == AttackType.PRIVILEGE_ABUSE
            and e.evidence.get("detection") == "undeclared_egress"
        ]
        assert len(egress_events) == 0


# ==================== HMAC 签名测试 ====================


class TestHMACSignature:
    """ObservationEvent HMAC 签名完整性"""

    @pytest.mark.asyncio
    async def test_events_are_hmac_signed(self) -> None:
        """所有事件必须带 HMAC 签名 (hmac_key 非空时)"""
        probe = _make_probe()
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://evil.com/pixel.gif",
                response_body=_1x1_GIF_BYTES,
                response_headers={"content-type": "image/gif"},
            )
        )
        events = await probe.poll()
        await probe.stop()

        assert len(events) >= 1
        for event in events:
            assert event.hash, "Event missing HMAC hash"
            assert len(event.hash) == 64, "HMAC-SHA256 should be 64 hex chars"
            assert verify_event_hash(event, HMAC_KEY), "HMAC verification failed"

    @pytest.mark.asyncio
    async def test_unsigned_when_no_hmac_key(self) -> None:
        """hmac_key 为空 → 事件不签名 (hash 为空)"""
        probe = NetworkEgressProbe(
            config=ProbeConfig(hmac_key=b"", poll_interval=0.01),
        )
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://t.com/pixel",
                response_body=_1x1_GIF_BYTES,
            )
        )
        events = await probe.poll()
        await probe.stop()

        assert len(events) >= 1
        for event in events:
            assert event.hash == ""


# ==================== Probe 生命周期测试 ====================


class TestProbeLifecycle:
    """Probe 生命周期 — start/stop 幂等, health_check"""

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        probe = _make_probe()
        await probe.start()
        await probe.start()  # 幂等
        assert probe._started is True
        await probe.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        probe = _make_probe()
        await probe.start()
        await probe.stop()
        await probe.stop()  # 幂等
        assert probe._started is False

    @pytest.mark.asyncio
    async def test_poll_before_start_returns_empty(self) -> None:
        probe = _make_probe()
        events = await probe.poll()
        assert events == []

    @pytest.mark.asyncio
    async def test_submit_flow_before_start_noop(self) -> None:
        probe = _make_probe()
        await probe.submit_flow(_make_flow(url="https://x.com/pixel"))
        # 未 start,队列应为空
        await probe.start()
        events = await probe.poll()
        assert events == []
        await probe.stop()

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        probe = _make_probe()
        await probe.start()
        healthy = await probe.health_check()
        assert healthy is True
        await probe.stop()

    def test_probe_name(self) -> None:
        probe = _make_probe()
        assert probe.probe_name == "network_egress"

    def test_snapshot_stats(self) -> None:
        probe = _make_probe(
            declared_endpoints=("api.anthropic.com",)
        )
        stats = probe.snapshot_stats()
        assert stats["flows_seen"] == 0
        assert stats["events_emitted"] == 0
        assert stats["declared_endpoints_count"] == 1


# ==================== 背压测试 ====================


class TestBackpressure:
    """队列满时的背压行为"""

    @pytest.mark.asyncio
    async def test_queue_full_drops_oldest(self) -> None:
        """队列满 → 丢弃最旧记录,新记录仍可入队"""
        # 用小容量队列测试 — 直接构造 probe 后替换 _queue
        probe = _make_probe()
        # 替换为小容量队列 (maxsize=2)
        probe._queue = asyncio.Queue(maxsize=2)
        await probe.start()

        # 用会触发检测的 flow (像素 URL) 以便统计
        await probe.submit_flow(
            _make_flow(url="https://a.com/pixel", response_body=b"")
        )
        await probe.submit_flow(
            _make_flow(url="https://b.com/pixel", response_body=b"")
        )
        # 队列满,第三个应丢弃最旧的 (a.com)
        await probe.submit_flow(
            _make_flow(url="https://c.com/pixel", response_body=b"")
        )

        events = await probe.poll()
        await probe.stop()

        # 应只处理 2 条 (容量 2),丢弃了最旧的 a.com
        stats = probe.snapshot_stats()
        assert stats["flows_seen"] == 2, (
            f"Expected 2 flows processed, got {stats['flows_seen']}"
        )
        # b.com 和 c.com 的 URL 都含 "pixel" → 每条至少 1 个像素事件
        pixel_events = [
            e for e in events if e.attack_type == AttackType.PIXEL_TRACKING
        ]
        assert len(pixel_events) == 2


# ==================== 多检测器协同测试 ====================


class TestMultipleDetectors:
    """同一 flow 触发多个检测器"""

    @pytest.mark.asyncio
    async def test_pixel_plus_stego_plus_egress(self) -> None:
        """同一 flow 同时触发像素/隐写/未声明外联 → 多个事件"""
        probe = _make_probe(
            declared_endpoints=("api.anthropic.com",)
        )
        await probe.start()
        await probe.submit_flow(
            _make_flow(
                url="https://evil.com/pixel.gif",
                response_headers={"content-type": "image/gif"},
                response_body=_1x1_GIF_BYTES + b'{"date":"2024/01/15"}',
                agent_id="claude-code",
            )
        )
        events = await probe.poll()
        await probe.stop()

        attack_types = {e.attack_type for e in events}
        # 至少触发像素 + 未声明外联 (隐写也可能触发,因 body 含 /)
        assert AttackType.PIXEL_TRACKING in attack_types
        assert AttackType.PRIVILEGE_ABUSE in attack_types
