"""test_daemon — SentinelDaemon 生命周期与事件流测试

覆盖验收标准:
- 1.1-A1: start() 后 5 秒内能采集到首个 ObservationEvent
- 1.1-A5: 关闭时 drain queue,无事件丢失
- 1.1-A6: sentinel overhead ≤ 15% CPU (此处验证功能,性能基准另测)
- 1.1-A7: ObservationEvent.hash = HMAC-SHA256(...)
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from maref.sentinel.daemon import SentinelDaemon
from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.probes.base import Probe, ProbeConfig

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-daemon-hmac-key"


class _MockProbe(Probe):
    """测试用 Mock Probe — 可控制 poll() 返回的事件"""

    def __init__(self, name: str, events: list[ObservationEvent] | None = None) -> None:
        self._name = name
        self._events = events or []
        self._config = ProbeConfig(poll_interval=0.05, hmac_key=HMAC_KEY)
        self._started = False
        self._poll_count = 0

    @property
    def probe_name(self) -> str:
        return self._name

    async def start(self) -> None:
        self._started = True

    async def poll(self) -> list[ObservationEvent]:
        self._poll_count += 1
        return list(self._events)

    async def stop(self) -> None:
        self._started = False

    def set_events(self, events: list[ObservationEvent]) -> None:
        self._events = events


def _make_event(
    source: str = "test",
    severity: Severity = Severity.LOW,
    subject: str = "pid:1",
    attack_type: AttackType = AttackType.NONE,
) -> ObservationEvent:
    """创建已签名的测试事件"""
    event = ObservationEvent(
        source=source,
        severity=severity,
        subject=subject,
        attack_type=attack_type,
        evidence={"test": True},
    )
    return event.with_hash(HMAC_KEY)


class TestDaemonLifecycle:
    """Daemon 生命周期测试"""

    async def test_start_stop_idempotent(self) -> None:
        """start/stop 幂等 — 重复调用无副作用"""
        probe = _MockProbe("test")
        daemon = SentinelDaemon(probes=[probe], hmac_key=HMAC_KEY)

        await daemon.start()
        assert daemon._started is True

        # 重复 start 无副作用
        await daemon.start()
        assert daemon._started is True

        await daemon.stop()
        assert daemon._started is False

        # 重复 stop 无副作用
        await daemon.stop()
        assert daemon._started is False

    async def test_start_with_no_probes(self) -> None:
        """无 Probe 也能启动"""
        daemon = SentinelDaemon(probes=[], hmac_key=HMAC_KEY)
        await daemon.start()
        assert daemon._started is True
        await daemon.stop()

    async def test_start_probe_failure_degraded(self) -> None:
        """Probe 启动失败 → degraded 状态"""
        failing_probe = _MockProbe("failing")
        failing_probe.start = AsyncMock(side_effect=RuntimeError("start failed"))

        daemon = SentinelDaemon(probes=[failing_probe], hmac_key=HMAC_KEY)
        await daemon.start()
        assert daemon._degraded is True
        assert "start failed" in daemon._degraded_reason
        await daemon.stop()


class TestDaemonEventFlow:
    """Daemon 事件流测试 — 覆盖 1.1-A1, A5"""

    async def test_first_event_within_5_seconds(self) -> None:
        """1.1-A1: start() 后 5 秒内能采集到首个 ObservationEvent"""
        event = _make_event(source="test", severity=Severity.HIGH)
        probe = _MockProbe("test", events=[event])

        received: list[list[ObservationEvent]] = []

        def callback(events: list[ObservationEvent]) -> None:
            received.append(events)

        daemon = SentinelDaemon(
            probes=[probe],
            alert_callback=callback,
            hmac_key=HMAC_KEY,
            batch_interval=0.05,
            batch_size=1,
        )

        await daemon.start()
        # 等待最多 5 秒
        start_time = time.time()
        while time.time() - start_time < 5.0 and not received:
            await asyncio.sleep(0.05)

        await daemon.stop()

        assert received, "No events received within 5 seconds"
        assert received[0][0].source == "test"

    async def test_drain_queue_on_stop(self) -> None:
        """1.1-A5: 关闭时 drain queue,无事件丢失"""
        # 生成 10 个事件
        events = [_make_event(source="test") for _ in range(10)]
        probe = _MockProbe("test", events=events)

        received: list[ObservationEvent] = []

        def callback(events_list: list[ObservationEvent]) -> None:
            received.extend(events_list)

        daemon = SentinelDaemon(
            probes=[probe],
            alert_callback=callback,
            hmac_key=HMAC_KEY,
            batch_interval=0.5,  # 长 interval,让事件堆积在 queue
            batch_size=100,  # 大 batch_size,让 batch loop 不频繁触发
        )

        await daemon.start()
        # 等待 poll loop 至少跑一次
        await asyncio.sleep(0.3)
        await daemon.stop()

        # drain 应该把 queue 中的事件全部推送
        assert len(received) >= 10, f"Expected >= 10 events, got {len(received)}"

    async def test_snapshot_returns_stats(self) -> None:
        """snapshot() 返回正确的统计数据"""
        event = _make_event(source="test", severity=Severity.HIGH)
        probe = _MockProbe("test", events=[event])

        daemon = SentinelDaemon(
            probes=[probe],
            alert_callback=lambda e: None,
            hmac_key=HMAC_KEY,
            batch_interval=0.05,
        )

        await daemon.start()
        await asyncio.sleep(0.3)  # 等待事件流入
        snap = await daemon.snapshot()
        await daemon.stop()

        assert snap["backend_name"] == "python_psutil"
        assert "test" in snap["probes_active"]
        assert snap["events_total"] >= 1
        assert snap["events_by_severity"]["HIGH"] >= 1
        assert snap["uptime_seconds"] > 0


class TestDaemonBackpressure:
    """Daemon 背压降级测试"""

    async def test_critical_sync_push_when_queue_full(self) -> None:
        """Queue 满时 CRITICAL 事件同步直推"""
        received: list[ObservationEvent] = []

        def callback(events: list[ObservationEvent]) -> None:
            received.extend(events)

        # queue_maxsize=1 让 Queue 很快满
        daemon = SentinelDaemon(
            probes=[],
            alert_callback=callback,
            hmac_key=HMAC_KEY,
            queue_maxsize=1,
            batch_interval=10.0,  # 不让 batch loop 消费
        )

        await daemon.start()

        # 先填满 queue
        event1 = _make_event(severity=Severity.LOW)
        await daemon.ingest(event1)

        # CRITICAL 事件 — 应该同步直推
        critical = _make_event(severity=Severity.CRITICAL, attack_type=AttackType.PRIVILEGE_ABUSE)
        await daemon.ingest(critical)

        await daemon.stop()

        # CRITICAL 应该被直推
        assert any(e.event_id == critical.event_id for e in received)

    async def test_low_dropped_when_queue_full(self) -> None:
        """Queue 满时 LOW 事件被丢弃"""
        received: list[ObservationEvent] = []

        def callback(events: list[ObservationEvent]) -> None:
            received.extend(events)

        daemon = SentinelDaemon(
            probes=[],
            alert_callback=callback,
            hmac_key=HMAC_KEY,
            queue_maxsize=1,
            batch_interval=10.0,  # 不让 batch loop 消费
        )

        await daemon.start()

        # 填满 queue
        event1 = _make_event(severity=Severity.LOW)
        await daemon.ingest(event1)

        # 第二个 LOW 事件 — 应该被丢弃
        event2 = _make_event(severity=Severity.LOW)
        await daemon.ingest(event2)

        await daemon.stop()

        # event2 应该被丢弃 (不在 received 中,除非 flush 时拿到 queue 里的 event1)
        assert daemon._events_dropped >= 1


class TestDaemonSubscribe:
    """Daemon subscribe() 流式订阅测试"""

    async def test_subscribe_receives_events(self) -> None:
        """subscribe() 能收到对应 Probe 的事件"""
        event = _make_event(source="process", severity=Severity.HIGH)
        probe = _MockProbe("process", events=[event])

        daemon = SentinelDaemon(
            probes=[probe],
            alert_callback=lambda e: None,
            hmac_key=HMAC_KEY,
            batch_interval=0.05,
        )

        await daemon.start()

        # 启动 subscriber
        received: list[ObservationEvent] = []

        async def subscriber() -> None:
            async for evt in daemon.subscribe("process"):
                received.append(evt)
                if len(received) >= 1:
                    break

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.5)  # 等待事件流入
        sub_task.cancel()
        try:
            await sub_task
        except asyncio.CancelledError:
            pass

        await daemon.stop()

        assert len(received) >= 1
        assert received[0].source == "process"


class TestDaemonAsyncCallback:
    """Daemon 异步 callback 测试"""

    async def test_async_callback(self) -> None:
        """异步 alert_callback 正常工作"""
        event = _make_event(source="test")
        probe = _MockProbe("test", events=[event])

        received: list[ObservationEvent] = []

        async def async_callback(events: list[ObservationEvent]) -> None:
            await asyncio.sleep(0.01)  # 模拟异步处理
            received.extend(events)

        daemon = SentinelDaemon(
            probes=[probe],
            alert_callback=async_callback,
            hmac_key=HMAC_KEY,
            batch_interval=0.05,
            batch_size=1,
        )

        await daemon.start()
        await asyncio.sleep(0.5)
        await daemon.stop()

        assert len(received) >= 1
