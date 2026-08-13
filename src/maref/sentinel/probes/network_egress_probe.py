"""
NetworkEgressProbe — 出站网络流量检测 (攻击 ① ④ + 未声明外联)

基于 mitmproxy 解密后的 HTTPS 流量记录,检测三类恶意行为:
1. 邮件像素追踪 (攻击 ①): 1x1 透明 GIF/PNG 请求,用于追踪用户是否打开邮件/触发某动作
   Claude Code 被指用此手法在用户不知情下上报行为指纹。
2. 日期分隔符隐写 (攻击 ④): 在 HTTP 响应日期字段中用 / 替换 -,
   每个分隔符选择编码 1 bit,实现隐蔽通信信道。
3. 未声明域名外联: Agent 连接的域名不在其 SignedAgentCard.declared_endpoints 中。

设计:
- FlowRecord 是 mitmproxy HTTPFlow 的脱敏快照,由 SentinelMitmAddon 产出。
- NetworkEgressProbe 不直接依赖 mitmproxy,只消费 FlowRecord,便于无 mitmproxy 环境下测试。
- 三个 Detector 是纯函数式规则,可独立单测。
- Daemon 通过 poll() 拉取事件;mitm_addon 通过 submit_flow() 推入队列。

验收标准:
- 1.2-A1: NetworkEgressProbe 对 1x1 透明像素 URL 检出率 ≥ 90%, 误报率 ≤ 5%
- 1.2-A2: NetworkEgressProbe 对日期分隔符 / 替换 - 的隐写检出率 ≥ 85%
- 1.2-A3: NetworkEgressProbe 对未在 declared_endpoints 中的外联域名检出率 100%
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.probes.base import Probe, ProbeConfig

# 1x1 透明 GIF 的 magic bytes (GIF89a + 1x1 logical screen descriptor)
_GIF89A_1x1_PREFIX = b"GIF89a\x01\x00\x01\x00"
_GIF87A_1x1_PREFIX = b"GIF87a\x01\x00\x01\x00"
# 1x1 透明 PNG signature + IHDR chunk (width=1, height=1)
_PNG_1x1_PREFIX = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"

# 像素追踪常见 URL 关键词 (case-insensitive)
_PIXEL_URL_KEYWORDS: tuple[str, ...] = (
    "pixel",
    "beacon",
    "tracker",
    "tracking",
    "open.gif",
    "blank.gif",
    "spacer.gif",
    "1x1",
    "1x1.gif",
    "1x1.png",
    "pixel.gif",
    "track.gif",
    "utm.gif",
    "__utm.gif",
    "notify.gif",
    "ping",
    "pixel.png",
)

# 像素追踪常见响应头标记
_PIXEL_HEADER_MARKERS: tuple[str, ...] = (
    "x-pixel",
    "x-tracker",
    "x-beacon-id",
    "x-track",
)

# 日期分隔符隐写检测的正则 — 匹配 YYYY-MM-DD 或 YYYY/MM/DD 混用
# 攻击者用 / 和 - 的选择编码 1 bit,在看似正常的日期中隐藏数据
_DATE_SLASH_PATTERN = re.compile(rb"\b(\d{4})/(\d{1,2})/(\d{1,2})\b")
_DATE_DASH_PATTERN = re.compile(rb"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
# 更宽松的日期模式 (含时间) — 用于检测日期中的 / 异常
_DATE_TIME_SLASH_PATTERN = re.compile(
    rb"\b(\d{4})/(\d{1,2})/(\d{1,2})[ T](\d{1,2}):(\d{1,2}):(\d{1,2})\b"
)


@dataclass(frozen=True)
class FlowRecord:
    """mitmproxy HTTPFlow 的脱敏快照 — NetworkEgressProbe 的输入

    由 SentinelMitmAddon 产出,推入 NetworkEgressProbe 的内部队列。
    不直接持有 mitmproxy 对象,保证 probe 与 mitmproxy 解耦。

    Attributes:
        flow_id: 唯一标识 (UUID)
        timestamp: unix timestamp (秒)
        method: HTTP 方法 (GET/POST/...)
        url: 完整 URL (含 scheme + host + path + query)
        request_headers: 请求头 (键小写)
        request_body: 请求体 (bytes,可能为空)
        status_code: 响应状态码 (0 = 无响应/被拦截)
        response_headers: 响应头 (键小写)
        response_body: 响应体 (bytes,可能为空)
        client_ip: 客户端 IP
        agent_id: 关联的 Agent ID (从 mitmproxy 上游元数据填充,可为空)
    """

    flow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = 0.0
    method: str = "GET"
    url: str = ""
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: bytes = b""
    status_code: int = 0
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: bytes = b""
    client_ip: str = ""
    agent_id: str = ""

    @property
    def host(self) -> str:
        """从 URL 提取主机名 (lowercase)"""
        try:
            return urlparse(self.url).hostname or ""
        except Exception:
            return ""

    @property
    def path(self) -> str:
        """从 URL 提取路径"""
        try:
            return urlparse(self.url).path or "/"
        except Exception:
            return "/"

    @property
    def content_type(self) -> str:
        """响应 Content-Type (lowercase)"""
        return self.response_headers.get("content-type", "").lower()


class NetworkEgressProbe(Probe):
    """出站网络流量检测 Probe — mitmproxy 解密后的 HTTPS 流量分析

    工作流:
        mitmproxy addon 捕获 flow → 转换为 FlowRecord → submit_flow() 入队
        → Daemon poll() 拉取 → 三类 Detector 并行检测 → 产出 ObservationEvent

    三个 Detector:
        1. _detect_pixel_tracking — 1x1 透明像素 (攻击 ①)
        2. _detect_date_steganography — 日期分隔符隐写 (攻击 ④)
        3. _detect_undeclared_egress — 未声明域名外联

    用法:
        probe = NetworkEgressProbe(
            config=ProbeConfig(hmac_key=key),
            declared_endpoints=("api.anthropic.com", "api.openai.com"),
        )
        await probe.start()
        await probe.submit_flow(flow_record)  # mitmproxy addon 调用
        events = await probe.poll()           # Daemon 周期性调用
        await probe.stop()
    """

    def __init__(
        self,
        config: ProbeConfig,
        declared_endpoints: tuple[str, ...] = (),
    ) -> None:
        """
        Args:
            config: Probe 配置 (含 hmac_key, poll_interval)
            declared_endpoints: 已声明的合法外联域名 (来自 SignedAgentCard.endpoints)
                                空元组 = M1.2 不启用未声明外联检测 (M4 接入 SignedAgentCardStore)
        """
        self._config = config
        self._declared_endpoints = {h.lower() for h in declared_endpoints if h}
        self._started: bool = False
        self._queue: asyncio.Queue[FlowRecord] = asyncio.Queue(maxsize=10000)
        self._flows_seen: int = 0
        self._events_emitted: int = 0

    @property
    def probe_name(self) -> str:
        return "network_egress"

    async def start(self) -> None:
        """初始化 Probe — 幂等"""
        if self._started:
            return
        self._started = True
        self._flows_seen = 0
        self._events_emitted = 0

    async def stop(self) -> None:
        """释放资源 — 幂等。不 drain 队列 (Daemon 负责最终 flush)。"""
        self._started = False

    async def submit_flow(self, record: FlowRecord) -> None:
        """提交一条 FlowRecord 到内部队列 (由 SentinelMitmAddon 调用)

        若队列已满,丢弃最旧记录并计数 (背压保护)。
        """
        if not self._started:
            return
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            pass

    async def poll(self) -> list[ObservationEvent]:
        """执行一次检测 — 排空当前队列中的所有 FlowRecord"""
        if not self._started:
            return []

        events: list[ObservationEvent] = []
        records: list[FlowRecord] = []
        while not self._queue.empty():
            try:
                records.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        for record in records:
            self._flows_seen += 1
            events.extend(self._detect_pixel_tracking(record))
            events.extend(self._detect_date_steganography(record))
            events.extend(self._detect_undeclared_egress(record))

        self._events_emitted += len(events)
        return events

    async def health_check(self) -> bool:
        """健康检查 — 队列未超载即健康"""
        return self._queue.qsize() < self._queue.maxsize

    def _detect_pixel_tracking(self, record: FlowRecord) -> list[ObservationEvent]:
        """检测 1x1 透明像素追踪 (攻击 ①) — 多重证据融合

        检测规则 (任一命中即告警,多重命中提升置信度):
        1. URL 含像素追踪关键词 (pixel/beacon/tracker/1x1/...)
        2. 响应体为 1x1 GIF/PNG magic bytes
        3. 响应 Content-Type 为 image/gif 或 image/png 且 body ≤ 100 字节
        4. 响应头含 X-Pixel/X-Tracker/X-Beacon 标记
        """
        signals: list[str] = []
        url_lower = record.url.lower()
        path_lower = record.path.lower()

        # 规则 1: URL 关键词
        for kw in _PIXEL_URL_KEYWORDS:
            if kw in url_lower:
                signals.append(f"url_keyword:{kw}")
                break

        # 规则 2: 响应体 magic bytes
        body = record.response_body
        if body:
            if body.startswith((_GIF89A_1x1_PREFIX, _GIF87A_1x1_PREFIX)):
                signals.append("body:1x1_gif_magic")
            elif body.startswith(_PNG_1x1_PREFIX):
                signals.append("body:1x1_png_magic")

        # 规则 3: Content-Type + 小体积
        ct = record.content_type
        if ct and ("image/gif" in ct or "image/png" in ct) and 0 < len(body) <= 100:
            signals.append(f"small_image:{ct}:{len(body)}b")

        # 规则 4: 响应头标记
        for header_name, header_value in record.response_headers.items():
            h_lower = header_name.lower()
            for marker in _PIXEL_HEADER_MARKERS:
                if marker in h_lower:
                    signals.append(f"header_marker:{header_name}")
                    break
            if header_value and any(kw in header_value.lower() for kw in _PIXEL_URL_KEYWORDS):
                signals.append(f"header_value_kw:{header_name}")

        if not signals:
            return []

        # 多重信号提升严重度: ≥3 个信号 = CRITICAL, 2 个 = HIGH, 1 个 = MEDIUM
        severity = (
            Severity.CRITICAL
            if len(signals) >= 3
            else Severity.HIGH
            if len(signals) == 2
            else Severity.MEDIUM
        )
        return [
            self._make_event(
                record,
                severity=severity,
                attack_type=AttackType.PIXEL_TRACKING,
                evidence={
                    "detection": "pixel_tracking",
                    "url": record.url,
                    "host": record.host,
                    "path": path_lower,
                    "signals": signals,
                    "signal_count": len(signals),
                    "response_body_size": len(body),
                    "content_type": ct,
                    "method": record.method,
                    "flow_id": record.flow_id,
                },
            )
        ]

    def _detect_date_steganography(self, record: FlowRecord) -> list[ObservationEvent]:
        """检测日期分隔符隐写 (攻击 ④) — / 替换 - 编码 bit

        Claude Code 被指在 HTTP 响应日期字段中用 / 和 - 交替作为分隔符,
        每个分隔符选择编码 1 bit,实现隐蔽通信。

        检测规则:
        1. 响应体含 YYYY/MM/DD 模式 (ISO 标准为 YYYY-MM-DD,用 / 即可疑)
        2. 同一响应中 / 和 - 日期模式共存 (强隐写信号)
        3. 日期字段 (Date, Last-Modified, Expires) 中出现 /
        """
        signals: list[str] = []
        body = record.response_body

        # 规则 1: 响应体含 / 分隔的日期
        slash_matches = _DATE_SLASH_PATTERN.findall(body)
        if slash_matches:
            signals.append(f"body_slash_dates:{len(slash_matches)}")

        # 规则 2: 同一响应中 / 和 - 日期共存 (强信号)
        dash_matches = _DATE_DASH_PATTERN.findall(body)
        if slash_matches and dash_matches:
            signals.append(f"mixed_separators:slash={len(slash_matches)},dash={len(dash_matches)}")

        # 规则 3: 日期字段中出现 / (HTTP 头 Date/Last-Modified/Expires)
        date_headers = ("date", "last-modified", "expires", "if-modified-since")
        for h_name in date_headers:
            h_value = record.response_headers.get(h_name, "")
            if h_value and "/" in h_value:
                # 标准 HTTP date 格式: "Mon, 15 Jan 2024 12:00:00 GMT" — 不含 /
                # 含 / 即异常 (可能是隐写或非标准格式)
                if _DATE_SLASH_PATTERN.search(h_value.encode("utf-8", errors="ignore")):
                    signals.append(f"date_header_slash:{h_name}")

        # 规则 4: 日期时间模式中的 / (含时间戳)
        slash_datetime_matches = _DATE_TIME_SLASH_PATTERN.findall(body)
        if slash_datetime_matches:
            signals.append(f"body_slash_datetime:{len(slash_datetime_matches)}")

        if not signals:
            return []

        # 混合分隔符 (规则 2) 或日期头含 / (规则 3) → CRITICAL
        # 单独 / 分隔 → HIGH
        has_strong = any("mixed_separators" in s or "date_header_slash" in s for s in signals)
        severity = Severity.CRITICAL if has_strong else Severity.HIGH
        return [
            self._make_event(
                record,
                severity=severity,
                attack_type=AttackType.STEGANOGRAPHY,
                evidence={
                    "detection": "date_separator_steganography",
                    "url": record.url,
                    "host": record.host,
                    "signals": signals,
                    "slash_date_count": len(slash_matches),
                    "dash_date_count": len(dash_matches),
                    "flow_id": record.flow_id,
                },
            )
        ]

    def _detect_undeclared_egress(self, record: FlowRecord) -> list[ObservationEvent]:
        """检测未声明域名外联 — Agent 连接的域名不在 declared_endpoints 中

        M1.2 阶段 declared_endpoints 由构造函数传入 (通常来自 SignedAgentCard.endpoints)。
        M4 阶段 SignedAgentCardStore.compare_declared_vs_observed 会做更深度对比。

        检测规则:
        - 提取 URL host
        - 若 declared_endpoints 非空且 host 不在其中 → CRITICAL
        - 若 declared_endpoints 为空 (M1.2 默认) → 不检测 (避免误报)
        """
        if not self._declared_endpoints:
            return []

        host = record.host.lower()
        if not host:
            return []

        # 精确匹配 或 后缀匹配 (子域名)
        for declared in self._declared_endpoints:
            if host == declared or host.endswith("." + declared):
                return []

        # 未匹配 — 未声明外联
        return [
            self._make_event(
                record,
                severity=Severity.CRITICAL,
                attack_type=AttackType.PRIVILEGE_ABUSE,
                evidence={
                    "detection": "undeclared_egress",
                    "url": record.url,
                    "host": host,
                    "declared_endpoints": sorted(self._declared_endpoints),
                    "method": record.method,
                    "flow_id": record.flow_id,
                    "agent_id": record.agent_id,
                },
            )
        ]

    def _make_event(
        self,
        record: FlowRecord,
        severity: Severity,
        attack_type: AttackType,
        evidence: dict[str, Any],
    ) -> ObservationEvent:
        """创建已签名的 ObservationEvent"""
        subject = f"agent:{record.agent_id}" if record.agent_id else f"host:{record.host}"
        event = ObservationEvent(
            source=self.probe_name,
            severity=severity,
            subject=subject,
            attack_type=attack_type,
            evidence=evidence,
        )
        if self._config.hmac_key:
            event = event.with_hash(self._config.hmac_key)
        return event

    def snapshot_stats(self) -> dict[str, Any]:
        """返回 probe 内部统计 (供 Daemon.snapshot() 聚合)"""
        return {
            "flows_seen": self._flows_seen,
            "events_emitted": self._events_emitted,
            "queue_size": self._queue.qsize(),
            "queue_maxsize": self._queue.maxsize,
            "declared_endpoints_count": len(self._declared_endpoints),
        }
