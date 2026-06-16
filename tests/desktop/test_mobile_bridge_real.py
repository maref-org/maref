"""Real mode tests for MAREF MobileBridge.

Tests device registration, discovery, session isolation, task dispatch
with idempotency, and real mode enable/disable. All tests work without
network access (localhost-only).
"""

from __future__ import annotations

import time

import pytest

from maref.desktop.mobile_bridge import (
    BridgeTask,
    DeviceDiscovery,
    DeviceInfo,
    DevicePlatform,
    DeviceType,
    MobileBridge,
    SessionManager,
    TaskPriority,
    TaskQueue,
    TaskStatus,
)


class TestDeviceRegistration:
    """Test manual device registration and discovery (non-mDNS)."""

    def test_register_device(self) -> None:
        dd = DeviceDiscovery(device_id="test-desktop", port=9099)
        device = DeviceInfo(
            device_id="mobile-001",
            name="Test Phone",
            device_type=DeviceType.MOBILE,
            platform=DevicePlatform.IOS,
            host="127.0.0.1",
            port=9090,
        )
        dd.register_device(device)
        assert dd.get_device("mobile-001") is not None
        assert dd.get_device("mobile-001").name == "Test Phone"

    def test_discover_all_devices(self) -> None:
        dd = DeviceDiscovery(device_id="test-desktop", port=9099)
        dd.register_device(
            DeviceInfo(
                device_id="mobile-001",
                name="Phone A",
                device_type=DeviceType.MOBILE,
                host="127.0.0.1",
                port=9090,
            )
        )
        dd.register_device(
            DeviceInfo(
                device_id="mobile-002",
                name="Phone B",
                device_type=DeviceType.MOBILE,
                host="127.0.0.1",
                port=9091,
            )
        )
        discovered = dd.discover()
        assert len(discovered) == 2

    def test_discover_by_type(self) -> None:
        dd = DeviceDiscovery(device_id="test-desktop", port=9099)
        dd.register_device(
            DeviceInfo(
                device_id="mobile-001",
                name="Phone A",
                device_type=DeviceType.MOBILE,
                host="127.0.0.1",
                port=9090,
            )
        )
        dd.register_device(
            DeviceInfo(
                device_id="desktop-002",
                name="Other Desktop",
                device_type=DeviceType.DESKTOP,
                host="127.0.0.1",
                port=9091,
            )
        )
        mobiles = dd.discover_by_type(DeviceType.MOBILE)
        desktops = dd.discover_by_type(DeviceType.DESKTOP)
        assert len(mobiles) == 1
        assert len(desktops) == 1

    def test_discover_by_capability(self) -> None:
        dd = DeviceDiscovery(device_id="test-desktop", port=9099)
        dd.register_device(
            DeviceInfo(
                device_id="mobile-001",
                name="Phone",
                capabilities=["screenshot", "touch"],
                host="127.0.0.1",
                port=9090,
            )
        )
        dd.register_device(
            DeviceInfo(
                device_id="desktop-002",
                name="Desktop",
                capabilities=["screenshot", "keyboard"],
                host="127.0.0.1",
                port=9091,
            )
        )
        touch_devices = dd.discover_by_capability("touch")
        screenshot_devices = dd.discover_by_capability("screenshot")
        assert len(touch_devices) == 1
        assert len(screenshot_devices) == 2

    def test_unregister_device(self) -> None:
        dd = DeviceDiscovery(device_id="test-desktop", port=9099)
        dd.register_device(
            DeviceInfo(
                device_id="mobile-001",
                name="Phone",
                host="127.0.0.1",
                port=9090,
            )
        )
        dd.unregister_device("mobile-001")
        assert dd.get_device("mobile-001") is None

    def test_local_device_info(self) -> None:
        dd = DeviceDiscovery(device_id="maref-desktop", port=9090)
        local = dd.local_device
        assert local.device_id == "maref-desktop"
        assert local.device_type == DeviceType.DESKTOP
        assert local.port == 9090

    def test_device_fingerprint(self) -> None:
        device = DeviceInfo(
            device_id="t-001",
            name="Test",
            platform=DevicePlatform.MACOS,
            host="127.0.0.1",
            port=9090,
        )
        fp = device.fingerprint
        assert isinstance(fp, str)
        assert len(fp) == 16

    def test_device_to_from_dict_roundtrip(self) -> None:
        device = DeviceInfo(
            device_id="roundtrip-001",
            name="Test Roundtrip",
            device_type=DeviceType.MOBILE,
            platform=DevicePlatform.ANDROID,
            host="127.0.0.1",
            port=9090,
            capabilities=["screenshot"],
        )
        data = device.to_dict()
        restored = DeviceInfo.from_dict(data)
        assert restored.device_id == device.device_id
        assert restored.name == device.name
        assert restored.device_type == device.device_type

    def test_check_online_localhost(self) -> None:
        dd = DeviceDiscovery(device_id="test-desktop", port=0)
        device = DeviceInfo(
            device_id="local-test",
            name="Local Device",
            host="127.0.0.1",
            port=0,
        )
        dd.register_device(device)
        status = dd.check_online(timeout=0.5)
        assert "local-test" in status


class TestSessionManagement:
    """Test session creation, isolation, and management."""

    def test_create_session(self) -> None:
        sm = SessionManager()
        session_id = sm.create_session("phone-001", "desktop-001")
        assert session_id.startswith("phone-001->desktop-001-")
        assert sm.get_session(session_id) is not None

    def test_session_isolation(self) -> None:
        sm = SessionManager()
        sid_a = sm.create_session("phone-A", "desktop-A")
        sid_b = sm.create_session("phone-B", "desktop-B")
        assert sid_a != sid_b
        sessions_a = sm.find_sessions_by_source("phone-A")
        sessions_b = sm.find_sessions_by_source("phone-B")
        assert len(sessions_a) == 1
        assert len(sessions_b) == 1
        assert sessions_a[0] != sessions_b[0]

    def test_close_session(self) -> None:
        sm = SessionManager()
        sid = sm.create_session("phone-001", "desktop-001")
        assert sm.close_session(sid) is True
        assert sm.close_session("nonexistent") is False

    def test_find_by_source_and_target(self) -> None:
        sm = SessionManager()
        sm.create_session("phone-1", "desktop-1")
        sm.create_session("phone-1", "desktop-2")
        by_source = sm.find_sessions_by_source("phone-1")
        assert len(by_source) == 2
        by_target = sm.find_sessions_by_target("desktop-1")
        assert len(by_target) == 1
        assert sm.find_sessions_by_source("nonexistent") == []

    def test_get_device_pairs(self) -> None:
        sm = SessionManager()
        sm.create_session("phone-1", "desktop-1")
        sm.create_session("phone-2", "desktop-1")
        pairs = sm.get_device_pairs()
        assert ("phone-1", "desktop-1") in pairs
        assert ("phone-2", "desktop-1") in pairs

    def test_get_active_sessions(self) -> None:
        sm = SessionManager()
        sid_a = sm.create_session("phone-1", "desktop-1")
        sid_b = sm.create_session("phone-1", "desktop-2")
        active = sm.get_active_sessions()
        assert len(active) == 2
        sm.close_session(sid_a)
        active_after = sm.get_active_sessions()
        assert len(active_after) == 1

    def test_session_with_context(self) -> None:
        sm = SessionManager()
        sid = sm.create_session("phone-1", "desktop-1", context={"app": "Finder"})
        session = sm.get_session(sid)
        assert session["context"] == {"app": "Finder"}

    def test_queue_per_session(self) -> None:
        sm = SessionManager()
        sid = sm.create_session("phone-1", "desktop-1")
        queue = sm.get_queue_for_session(sid)
        assert queue is not None
        assert queue.size == 0

        task = BridgeTask(
            name="test-task",
            source_device="phone-1",
            target_device="desktop-1",
        )
        queue.enqueue(task)
        assert queue.size == 1

    def test_closed_session_returns_none_queue(self) -> None:
        sm = SessionManager()
        sid = sm.create_session("phone-1", "desktop-1")
        sm.close_session(sid)
        queue = sm.get_queue_for_session(sid)
        assert queue is None


class TestTaskDispatch:
    """Test task queue operations including idempotency."""

    def test_enqueue_dequeue(self) -> None:
        tq = TaskQueue()
        task = BridgeTask(name="test-task", source_device="s", target_device="t")
        assert tq.enqueue(task) is True
        assert tq.size == 1
        dequeued = tq.dequeue()
        assert dequeued.task_id == task.task_id
        assert tq.size == 0

    def test_idempotency_deduplication(self) -> None:
        tq = TaskQueue()
        task_a = BridgeTask(
            name="a", source_device="s", target_device="t", idempotency_key="key-001"
        )
        task_b = BridgeTask(
            name="b", source_device="s", target_device="t", idempotency_key="key-001"
        )
        assert tq.enqueue(task_a) is True
        assert tq.enqueue(task_b) is False
        assert tq.size == 1

    def test_idempotency_different_keys(self) -> None:
        tq = TaskQueue()
        task_a = BridgeTask(name="a", idempotency_key="key-001")
        task_b = BridgeTask(name="b", idempotency_key="key-002")
        assert tq.enqueue(task_a) is True
        assert tq.enqueue(task_b) is True
        assert tq.size == 2

    def test_no_idempotency_key_allows_duplicates(self) -> None:
        tq = TaskQueue()
        task_a = BridgeTask(name="a", source_device="s", target_device="t")
        task_b = BridgeTask(name="b", source_device="s", target_device="t")
        assert tq.enqueue(task_a) is True
        assert tq.enqueue(task_b) is True
        assert tq.size == 2

    def test_priority_ordering(self) -> None:
        tq = TaskQueue()
        low = BridgeTask(name="low", priority=TaskPriority.LOW)
        high = BridgeTask(name="high", priority=TaskPriority.HIGH)
        urgent = BridgeTask(name="urgent", priority=TaskPriority.URGENT)
        tq.enqueue(low)
        tq.enqueue(high)
        tq.enqueue(urgent)
        first = tq.dequeue()
        assert first.priority == TaskPriority.URGENT

    def test_complete_task(self) -> None:
        tq = TaskQueue()
        task = BridgeTask(name="test", source_device="s", target_device="t")
        tq.enqueue(task)
        tq.complete(task.task_id, {"status": "ok"})
        completed = tq.get_completed()
        assert len(completed) == 1
        assert completed[0].status == TaskStatus.COMPLETED

    def test_fail_task(self) -> None:
        tq = TaskQueue()
        task = BridgeTask(name="test")
        tq.enqueue(task)
        tq.fail(task.task_id, "something broke")
        completed = tq.get_completed()
        assert completed[0].status == TaskStatus.FAILED
        assert completed[0].error == "something broke"

    def test_cancel_task(self) -> None:
        tq = TaskQueue()
        task = BridgeTask(name="test", source_device="s", target_device="t")
        tq.enqueue(task)
        assert tq.cancel(task.task_id) is True
        completed = tq.get_completed()
        assert completed[0].status == TaskStatus.CANCELLED

    def test_max_queue_size(self) -> None:
        tq = TaskQueue(max_queue_size=2)
        assert tq.enqueue(BridgeTask(name="a")) is True
        assert tq.enqueue(BridgeTask(name="b")) is True
        assert tq.enqueue(BridgeTask(name="c")) is False
        assert tq.size == 2

    def test_get_by_source(self) -> None:
        tq = TaskQueue()
        tq.enqueue(BridgeTask(name="a", source_device="phone-1", target_device="desktop-1"))
        tq.enqueue(BridgeTask(name="b", source_device="phone-2", target_device="desktop-1"))
        from_phone1 = tq.get_by_source("phone-1")
        assert len(from_phone1) == 1
        assert from_phone1[0].name == "a"

    def test_peek_does_not_remove(self) -> None:
        tq = TaskQueue()
        tq.enqueue(BridgeTask(name="test"))
        assert tq.peek() is not None
        assert tq.size == 1


class TestMobileBridgeFull:
    """Integration tests for the full MobileBridge pipeline."""

    def test_bridge_register_and_topology(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        device = DeviceInfo(
            device_id="phone-1",
            name="Test Phone",
            device_type=DeviceType.MOBILE,
            platform=DevicePlatform.IOS,
            host="127.0.0.1",
            port=9090,
        )
        bridge.register_mobile_device(device)
        topology = bridge.get_device_topology()
        assert topology["local"]["device_id"] == "desktop-1"
        assert len(topology["discovered"]) == 1

    def test_bridge_session_creation(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        sid = bridge.create_bridge_session("phone-1", "desktop-1")
        assert sid.startswith("phone-1->desktop-1-")
        topology = bridge.get_device_topology()
        assert topology["active_sessions"] == 1

    def test_bridge_dispatch_task(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        bridge.register_mobile_device(
            DeviceInfo(
                device_id="phone-1",
                name="Phone",
                host="127.0.0.1",
                port=9090,
            )
        )
        task = bridge.dispatch_task(
            source_device="phone-1",
            target_device="desktop-1",
            task_name="screenshot_request",
            payload={"region": "full"},
            priority=TaskPriority.HIGH,
        )
        assert task.task_id != ""
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.PENDING

    def test_bridge_dispatch_with_idempotency(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        task = bridge.dispatch_task(
            source_device="phone-1",
            target_device="desktop-1",
            task_name="duplicate_check",
            payload={},
            idempotency_key="dup-key-001",
        )
        assert task.idempotency_key == "dup-key-001"

    def test_bridge_task_lifecycle(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        task = bridge.dispatch_task(
            source_device="phone-1",
            target_device="desktop-1",
            task_name="lifecycle_test",
            payload={"action": "click"},
        )
        bridge.complete_task(task.task_id, {"x": 100, "y": 200})
        event_log = bridge.get_event_log()
        assert len(event_log) >= 2

    def test_bridge_fail_task(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        task = bridge.dispatch_task(
            source_device="phone-1",
            target_device="desktop-1",
            task_name="failing_task",
            payload={},
        )
        bridge.fail_task(task.task_id, "timeout")
        assert len(bridge.get_event_log()) >= 2

    def test_bridge_event_log_limit(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        for i in range(5):
            bridge.dispatch_task(
                source_device="phone-1",
                target_device="desktop-1",
                task_name=f"task-{i}",
                payload={},
            )
        log = bridge.get_event_log(limit=3)
        assert len(log) == 3

    def test_enable_real_mode(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        result = bridge.enable_real_mode(host="127.0.0.1", port=9099)
        assert result["enabled"] is True
        assert result["host"] == "127.0.0.1"
        assert result["port"] == 9099

    def test_disable_real_mode(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        bridge.enable_real_mode(host="127.0.0.1", port=9099)
        bridge.disable_real_mode()
        events = bridge.get_event_log()
        event_types = [e["event_type"] for e in events]
        assert "real_mode_disabled" in event_types

    def test_device_discovery_mdns_fallback(self) -> None:
        dd = DeviceDiscovery(device_id="test", port=9099)
        result = dd.start_mdns_advertisement()
        assert isinstance(result, bool)

    def test_device_discovery_mdns_discovery_fallback(self) -> None:
        dd = DeviceDiscovery(device_id="test", port=9099)
        discovered = dd.start_mdns_discovery(timeout=1.0)
        assert isinstance(discovered, list)

    def test_device_discovery_mdns_property(self) -> None:
        dd = DeviceDiscovery(device_id="test", port=9099)
        dd.start_mdns_advertisement()
        assert isinstance(dd.mdns_active, bool)
        dd.stop_mdns_advertisement()
        assert dd.mdns_active is False

    def test_bridge_one_to_n_topology(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        for i in range(3):
            bridge.register_mobile_device(
                DeviceInfo(
                    device_id=f"phone-{i}",
                    name=f"Phone {i}",
                    host="127.0.0.1",
                    port=9090 + i,
                )
            )
        topology = bridge.get_device_topology()
        assert len(topology["discovered"]) == 3
        assert topology["local"]["device_id"] == "desktop-1"

    @pytest.mark.slow
    def test_task_dispatch_timing(self) -> None:
        bridge = MobileBridge(device_id="desktop-1", port=9099)
        t0 = time.time()
        for i in range(100):
            bridge.dispatch_task(
                source_device="phone-1",
                target_device="desktop-1",
                task_name=f"perf-{i}",
                payload={},
            )
        elapsed = time.time() - t0
        assert elapsed < 1.0
