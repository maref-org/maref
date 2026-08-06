"""
SentinelDaemon — 观测神经核心事件循环

包含两部分:
1. Daemon — 抽象基类 (接口契约,与 ADR-006 一致)
2. SentinelDaemon — 具体实现 (M1,psutil-based 跨平台)

SentinelDaemon 职责:
- 管理 Probe 生命周期 (start/stop)
- 周期性调用 Probe.poll() 拉取事件 (asyncio poll loop)
- 事件入 asyncio.Queue (maxsize=10000)
- 后台 batch coroutine 批量推送 alert_callback (每 100ms 或 100 条)
- 背压降级: Queue 满时 CRITICAL/HIGH 同步直推, MEDIUM/LOW 丢弃+告警
- 健康检查 loop: 每 30s 检查 Probe 健康,失败则降级
- subscribe(): 流式订阅特定 Probe 事件 (供 CapabilityDriftDetector 等下游)

验收标准:
- 1.1-A1: start() 后 5 秒内能采集到首个 ObservationEvent
- 1.1-A5: 关闭时 drain queue,无事件丢失
- 1.1-A6: sentinel overhead ≤ 15% CPU (单核基准)
- 1.1-A7: ObservationEvent.hash = HMAC-SHA256(event_id+ts+subject+evidence)
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Any

from maref.sentinel.event import ObservationEvent, Severity
from maref.sentinel.probes.base import Probe, ProbeConfig

logger = logging.getLogger(__name__)

# 背压: Queue 满时的降级策略
_QUEUE_MAXSIZE: int = 10000
_BATCH_INTERVAL: float = 0.1  # 100ms
_BATCH_SIZE: int = 100
_HEALTH_CHECK_INTERVAL: float = 30.0  # 30s


class Daemon(ABC):
    """SentinelDaemon 抽象基类 — 所有平台 backend 必须实现

    M0 阶段: 仅接口骨架。
    M1 阶段: SentinelDaemon 提供具体实现。
    """

    @abstractmethod
    async def start(self) -> None:
        """启动所有 Probe + Backend,开始观测。幂等。"""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """优雅关闭: drain asyncio.Queue,确保无事件丢失,卸载 backend。"""
        raise NotImplementedError

    @abstractmethod
    async def snapshot(self) -> dict[str, Any]:
        """返回当前观测快照 (调试/健康检查用),不写审计日志。"""
        raise NotImplementedError

    @abstractmethod
    async def ingest(self, event: ObservationEvent) -> None:
        """Probe/Backend 推送事件入口。事件入 Queue,后台批量推送。"""
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, probe_name: str) -> AsyncIterator[ObservationEvent]:
        """订阅特定 Probe 的事件流 (供下游消费)。"""
        raise NotImplementedError


class SentinelDaemon(Daemon):
    """SentinelDaemon 具体实现 — M1 psutil-based 跨平台

    Usage:
        daemon = SentinelDaemon(
            probes=[ProcessProbe(config), EnvProbe(config), ...],
            alert_callback=my_callback,  # 接收 list[ObservationEvent]
            hmac_key=key,
        )
        await daemon.start()
        # ... Probe 自动轮询,事件自动批量推送 ...
        snapshot = await daemon.snapshot()
        await daemon.stop()

    alert_callback 签名:
        def my_callback(events: list[ObservationEvent]) -> None: ...
    或异步:
        async def my_callback(events: list[ObservationEvent]) -> None: ...

    M4 时 alert_callback 会被接线到 ThreatGovernanceBridge.batch_alerts。
    """

    def __init__(
        self,
        probes: list[Probe],
        alert_callback: Callable[[list[ObservationEvent]], Any] | None = None,
        hmac_key: bytes = b"",
        queue_maxsize: int = _QUEUE_MAXSIZE,
        batch_interval: float = _BATCH_INTERVAL,
        batch_size: int = _BATCH_SIZE,
        health_check_interval: float = _HEALTH_CHECK_INTERVAL,
    ) -> None:
        self._probes: list[Probe] = list(probes)
        self._alert_callback: Callable[[list[ObservationEvent]], Any] | None = alert_callback
        self._hmac_key: bytes = hmac_key
        self._queue: asyncio.Queue[ObservationEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._batch_interval: float = batch_interval
        self._batch_size: int = batch_size
        self._health_check_interval: float = health_check_interval

        # 运行时状态
        self._started: bool = False
        self._stopping: bool = False
        self._tasks: list[asyncio.Task[None]] = []
        self._subscribers: dict[str, list[asyncio.Queue[ObservationEvent]]] = {}

        # 统计
        self._events_total: int = 0
        self._events_by_severity: dict[str, int] = {s.value: 0 for s in Severity}
        self._events_by_attack_type: dict[str, int] = {}
        self._events_dropped: int = 0
        self._started_at: float = 0.0
        self._degraded: bool = False
        self._degraded_reason: str = ""

    async def start(self) -> None:
        """启动 Daemon — 启动所有 Probe + poll loop + batch coroutine + 健康检查"""
        if self._started:
            return
        self._started = True
        self._stopping = False
        self._started_at = time.time()

        # 1. 启动所有 Probe
        for probe in self._probes:
            try:
                await probe.start()
                logger.info("Probe %s started", probe.probe_name)
            except Exception as e:
                logger.exception("Probe %s start failed: %s", probe.probe_name, e)
                self._degraded = True
                self._degraded_reason = f"probe {probe.probe_name} failed: {e}"

        # 2. 启动 poll loop (每个 Probe 一个 task)
        for probe in self._probes:
            task = asyncio.create_task(self._poll_loop(probe), name=f"poll-{probe.probe_name}")
            self._tasks.append(task)

        # 3. 启动 batch coroutine
        batch_task = asyncio.create_task(self._batch_loop(), name="batch")
        self._tasks.append(batch_task)

        # 4. 启动健康检查 loop
        health_task = asyncio.create_task(self._health_loop(), name="health")
        self._tasks.append(health_task)

        logger.info("SentinelDaemon started with %d probes", len(self._probes))

    async def stop(self) -> None:
        """优雅关闭 — drain queue + 停止 Probe + 取消 task"""
        if not self._started:
            return
        self._stopping = True

        # 1. 停止所有 Probe (阻止新事件产生)
        for probe in self._probes:
            try:
                await probe.stop()
            except Exception as e:
                logger.exception("Probe %s stop failed: %s", probe.probe_name, e)

        # 2. 让 batch loop 有机会推送当前 batch (yield 后 batch loop 能检测
        #    _stopping=True 并在退出前 push batch)
        await asyncio.sleep(0)

        # 3. 取消所有后台 task (poll loop / batch loop / health)
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # 4. Drain queue — 确保无事件丢失 (1.1-A5)
        await self._flush_queue()

        self._started = False
        self._stopping = False
        logger.info(
            "SentinelDaemon stopped — total events: %d, dropped: %d",
            self._events_total,
            self._events_dropped,
        )

    async def ingest(self, event: ObservationEvent) -> None:
        """推送事件入口 — 背压降级策略

        Queue 满时:
        - CRITICAL/HIGH: 同步直推 alert_callback (绕过 Queue)
        - MEDIUM/LOW: 丢弃 + 写 LOW 级别 audit log (背压告警)
        """
        if not self._started or self._stopping:
            return

        # 推送到 subscriber queue (非阻塞)
        self._dispatch_to_subscribers(event)

        # Queue 满时的背压降级
        if self._queue.full():
            if event.severity in (Severity.CRITICAL, Severity.HIGH):
                # 高优先级: 同步直推
                await self._push_to_callback([event])
                self._update_stats(event)
                logger.warning(
                    "Queue full, sync pushed %s event %s",
                    event.severity.value,
                    event.event_id,
                )
            else:
                # 低优先级: 丢弃
                self._events_dropped += 1
                logger.warning(
                    "Queue full, dropped %s event %s (total dropped: %d)",
                    event.severity.value,
                    event.event_id,
                    self._events_dropped,
                )
            return

        # 正常入队
        try:
            self._queue.put_nowait(event)
            self._update_stats(event)
        except asyncio.QueueFull:
            # 竞态条件: put_nowait 仍可能抛 QueueFull
            self._events_dropped += 1

    async def snapshot(self) -> dict[str, Any]:
        """返回当前观测快照 (调试/健康检查用)"""
        return {
            "backend_name": "python_psutil",
            "backend_health": not self._degraded,
            "queue_size": self._queue.qsize(),
            "queue_maxsize": self._queue.maxsize,
            "probes_active": [p.probe_name for p in self._probes],
            "events_total": self._events_total,
            "events_by_severity": dict(self._events_by_severity),
            "events_by_attack_type": dict(self._events_by_attack_type),
            "events_dropped": self._events_dropped,
            "uptime_seconds": time.time() - self._started_at if self._started_at else 0,
            "degraded": self._degraded,
            "degraded_reason": self._degraded_reason,
            "subscriber_count": sum(len(qs) for qs in self._subscribers.values()),
        }

    def subscribe(self, probe_name: str) -> AsyncIterator[ObservationEvent]:
        """订阅特定 Probe 的事件流 — 返回异步生成器

        Usage:
            async for event in daemon.subscribe("process"):
                handle(event)
        """
        return self._subscribe_generator(probe_name)

    async def _subscribe_generator(self, probe_name: str) -> AsyncIterator[ObservationEvent]:
        """订阅生成器实现 — 从内部 queue 读取事件"""
        sub_queue: asyncio.Queue[ObservationEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.setdefault(probe_name, []).append(sub_queue)
        try:
            while self._started and not self._stopping:
                try:
                    event = await asyncio.wait_for(sub_queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    continue
        finally:
            # 清理 subscriber
            if probe_name in self._subscribers:
                self._subscribers[probe_name].remove(sub_queue)
                if not self._subscribers[probe_name]:
                    del self._subscribers[probe_name]

    def _dispatch_to_subscribers(self, event: ObservationEvent) -> None:
        """将事件分发到匹配的 subscriber queue (非阻塞)"""
        subs = self._subscribers.get(event.source, [])
        for sub_queue in subs:
            try:
                sub_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Subscriber queue full for %s, dropping event %s",
                    event.source,
                    event.event_id,
                )

    async def _poll_loop(self, probe: Probe) -> None:
        """Probe 轮询循环 — 按 poll_interval 调用 probe.poll()"""
        # 从 probe 的 config 获取 poll_interval
        config = getattr(probe, "_config", None)
        if isinstance(config, ProbeConfig):
            poll_interval: float = config.poll_interval
        else:
            poll_interval = 1.0

        while self._started and not self._stopping:
            try:
                events = await probe.poll()
                for event in events:
                    await self.ingest(event)
            except Exception as e:
                logger.exception("Probe %s poll error: %s", probe.probe_name, e)
                self._degraded = True
                self._degraded_reason = f"probe {probe.probe_name} poll error: {e}"
            await asyncio.sleep(poll_interval)

    async def _batch_loop(self) -> None:
        """批量推送循环 — 每 batch_interval 或 batch_size 条触发一次"""
        while self._started and not self._stopping:
            batch: list[ObservationEvent] = []
            deadline = time.time() + self._batch_interval
            # 在 stopping 时也继续收集已有事件 (不立即退出内层循环)
            try:
                while len(batch) < self._batch_size and time.time() < deadline:
                    try:
                        remaining = max(0.0, deadline - time.time())
                        event = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                        batch.append(event)
                    except asyncio.TimeoutError:
                        break
                    except asyncio.QueueEmpty:
                        break
            except asyncio.CancelledError:
                # 被 cancel 前先推送已收集的事件,防止事件丢失
                if batch:
                    await self._push_to_callback(batch)
                    logger.info("Batch loop cancelled, pushed %d remaining events", len(batch))
                raise
            if batch:
                await self._push_to_callback(batch)
            if not batch and self._stopping:
                # 停止中且无事件,退出
                break
            # 若没有事件,短暂 sleep 避免 busy loop
            if not batch:
                await asyncio.sleep(self._batch_interval)

    async def _health_loop(self) -> None:
        """健康检查循环 — 每 health_check_interval 检查 Probe 健康"""
        while self._started and not self._stopping:
            await asyncio.sleep(self._health_check_interval)
            for probe in self._probes:
                try:
                    healthy = await probe.health_check()
                    if not healthy:
                        logger.warning("Probe %s health check failed", probe.probe_name)
                        self._degraded = True
                        self._degraded_reason = (
                            f"probe {probe.probe_name} unhealthy"
                        )
                except Exception as e:
                    logger.exception("Probe %s health check error: %s", probe.probe_name, e)

    async def _push_to_callback(self, events: list[ObservationEvent]) -> None:
        """推送事件批量到 alert_callback (支持同步和异步 callback)"""
        if not self._alert_callback or not events:
            return
        try:
            result = self._alert_callback(events)
            # 如果 callback 返回 coroutine, await 它
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.exception("alert_callback error: %s", e)

    async def _flush_queue(self) -> None:
        """Drain queue — 关闭时确保无事件丢失"""
        batch: list[ObservationEvent] = []
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                batch.append(event)
            except asyncio.QueueEmpty:
                break
        if batch:
            await self._push_to_callback(batch)
            logger.info("Flushed %d remaining events on stop", len(batch))

    def _update_stats(self, event: ObservationEvent) -> None:
        """更新事件统计"""
        self._events_total += 1
        sev_key = event.severity.value
        self._events_by_severity[sev_key] = self._events_by_severity.get(sev_key, 0) + 1
        atk_key = event.attack_type.value
        self._events_by_attack_type[atk_key] = self._events_by_attack_type.get(atk_key, 0) + 1

    def detect_exfiltration(self, data: bytes, pid: int | None = None) -> bool:
        """检测数据外泄 — DataExfiltrationProbe 集成的入口点。

        ⚠️ M4 stub: 当前恒返回 False (向后兼容)。M6 红蓝对抗时将接入
        NetworkEgressProbe 的实际观测数据,实现真实外泄检测逻辑。

        Args:
            data: 可疑数据载荷
            pid: 目标进程 PID (None = 全量观测)

        Returns:
            True = 检测到外泄行为
        """
        return False
