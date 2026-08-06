from __future__ import annotations

from maref.desktop.mobile_bridge import (
    BridgeTask,
    ConnectionMethod,
    DeviceDiscovery,
    DeviceInfo,
    DevicePlatform,
    DeviceType,
    SessionManager,
    TaskPriority,
    TaskQueue,
    TaskStatus,
)


class TestEnums:
    def test_device_type(self) -> None:
        assert DeviceType.DESKTOP.value == "desktop"
        assert DeviceType.MOBILE.value == "mobile"
        assert DeviceType.SERVER.value == "server"
        assert DeviceType.IOT.value == "iot"
        assert DeviceType.UNKNOWN.value == "unknown"

    def test_device_platform(self) -> None:
        assert DevicePlatform.MACOS.value == "macos"
        assert DevicePlatform.WINDOWS.value == "windows"
        assert DevicePlatform.LINUX.value == "linux"
        assert DevicePlatform.ANDROID.value == "android"
        assert DevicePlatform.IOS.value == "ios"

    def test_task_priority(self) -> None:
        assert TaskPriority.LOW.value == "low"
        assert TaskPriority.URGENT.value == "urgent"

    def test_task_status(self) -> None:
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.TIMED_OUT.value == "timed_out"

    def test_connection_method(self) -> None:
        assert ConnectionMethod.LOCAL.value == "local"
        assert ConnectionMethod.CLOUD.value == "cloud"


class TestDeviceInfo:
    def test_defaults(self) -> None:
        info = DeviceInfo(device_id="d1", name="test-device")
        assert info.device_id == "d1"
        assert info.name == "test-device"
        assert info.device_type == DeviceType.UNKNOWN
        assert info.platform == DevicePlatform.UNKNOWN
        assert info.host == "localhost"
        assert info.port == 0
        assert info.capabilities == []
        assert info.connection_method == ConnectionMethod.LOCAL
        assert info.trust_score == 1.0
        assert info.is_online is True

    def test_with_values(self) -> None:
        info = DeviceInfo(
            device_id="d2",
            name="phone",
            device_type=DeviceType.MOBILE,
            platform=DevicePlatform.ANDROID,
            host="192.168.1.10",
            port=8080,
            capabilities=["screenshot", "input"],
            trust_score=0.85,
            is_online=False,
        )
        assert info.device_type == DeviceType.MOBILE
        assert info.fingerprint  # non-empty hash

    def test_to_dict(self) -> None:
        info = DeviceInfo(device_id="d1", name="test")
        d = info.to_dict()
        assert d["device_id"] == "d1"
        assert d["name"] == "test"
        assert d["device_type"] == "unknown"
        assert d["is_online"] is True

    def test_from_dict(self) -> None:
        info = DeviceInfo.from_dict(
            {
                "device_id": "d3",
                "name": "from-dict",
                "device_type": "mobile",
                "platform": "ios",
            }
        )
        assert info.device_id == "d3"
        assert info.device_type == DeviceType.MOBILE
        assert info.platform == DevicePlatform.IOS

    def test_fingerprint(self) -> None:
        info = DeviceInfo(device_id="xyz", name="node", host="10.0.0.1", port=5555)
        fp = info.fingerprint
        assert isinstance(fp, str)
        assert len(fp) == 16


class TestBridgeTask:
    def test_defaults(self) -> None:
        task = BridgeTask()
        assert task.task_id
        assert task.name == ""
        assert task.priority == TaskPriority.NORMAL
        assert task.status == TaskStatus.PENDING
        assert task.timeout_seconds == 60.0

    def test_with_values(self) -> None:
        task = BridgeTask(
            name="upload",
            source_device="d1",
            target_device="d2",
            payload={"file": "data"},
            priority=TaskPriority.HIGH,
            timeout_seconds=30.0,
            idempotency_key="key123",
        )
        assert task.name == "upload"
        assert task.priority == TaskPriority.HIGH
        assert task.timeout_seconds == 30.0
        assert task.idempotency_key == "key123"

    def test_to_dict(self) -> None:
        task = BridgeTask(name="test")
        d = task.to_dict()
        assert d["name"] == "test"
        assert "task_id" in d

    def test_from_dict(self) -> None:
        task = BridgeTask.from_dict({"name": "restored", "priority": "high"})
        assert task.name == "restored"
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.PENDING


class TestDeviceDiscovery:
    def test_init(self) -> None:
        dd = DeviceDiscovery(device_id="my-host", port=9999)
        assert dd.device_id == "my-host"
        assert dd.port == 9999
        assert dd.local_device.device_id == "my-host"
        assert dd.local_device.device_type == DeviceType.DESKTOP

    def test_register_and_discover(self) -> None:
        dd = DeviceDiscovery()
        dev = DeviceInfo(device_id="remote-1", name="remote")
        dd.register_device(dev)
        assert len(dd.discover()) == 1
        assert dd.get_device("remote-1") is dev

    def test_discover_by_type(self) -> None:
        dd = DeviceDiscovery()
        mobile = DeviceInfo(
            device_id="m1", name="m", device_type=DeviceType.MOBILE
        )
        desktop = DeviceInfo(
            device_id="d1", name="d", device_type=DeviceType.DESKTOP
        )
        dd.register_device(mobile)
        dd.register_device(desktop)
        mobiles = dd.discover_by_type(DeviceType.MOBILE)
        assert len(mobiles) == 1
        assert mobiles[0].device_id == "m1"

    def test_discover_by_capability(self) -> None:
        dd = DeviceDiscovery()
        dev = DeviceInfo(
            device_id="c1",
            name="c",
            capabilities=["screenshot", "input"],
        )
        dd.register_device(dev)
        results = dd.discover_by_capability("input")
        assert len(results) == 1
        results = dd.discover_by_capability("nonexistent")
        assert len(results) == 0

    def test_unregister(self) -> None:
        dd = DeviceDiscovery()
        dev = DeviceInfo(device_id="gone", name="gone")
        dd.register_device(dev)
        assert dd.get_device("gone") is dev
        dd.unregister_device("gone")
        assert dd.get_device("gone") is None


class TestSessionManager:
    def test_create_and_get(self) -> None:
        sm = SessionManager()
        session_id = sm.create_session(source_id="phone-1", target_id="mac-1")
        assert isinstance(session_id, str)
        assert "->" in session_id

        retrieved = sm.get_session(session_id)
        assert retrieved is not None
        assert retrieved["source_id"] == "phone-1"
        assert retrieved["target_id"] == "mac-1"

    def test_get_nonexistent(self) -> None:
        sm = SessionManager()
        assert sm.get_session("nope") is None

    def test_close_session(self) -> None:
        sm = SessionManager()
        session_id = sm.create_session(source_id="phone-1", target_id="mac-1")
        result = sm.close_session(session_id)
        assert result is True
        retrieved = sm.get_session(session_id)
        assert retrieved is not None
        assert retrieved["active"] is False

    def test_close_nonexistent(self) -> None:
        sm = SessionManager()
        assert sm.close_session("nope") is False


class TestTaskQueue:
    def test_enqueue_dequeue(self) -> None:
        queue = TaskQueue()
        task = BridgeTask(name="hello")
        result = queue.enqueue(task)
        assert result is True
        assert queue.size == 1

        dequeued = queue.dequeue()
        assert dequeued is not None
        assert dequeued.name == "hello"

    def test_dequeue_empty(self) -> None:
        queue = TaskQueue()
        assert queue.dequeue() is None

    def test_complete(self) -> None:
        queue = TaskQueue()
        task = BridgeTask(name="complete-me")
        queue.enqueue(task)
        queue.complete(task.task_id, {"success": True})
        completed = queue.get_completed()
        assert len(completed) == 1
        assert completed[0].name == "complete-me"
        assert completed[0].status == TaskStatus.COMPLETED

    def test_fail(self) -> None:
        queue = TaskQueue()
        task = BridgeTask(name="fail-me")
        queue.enqueue(task)
        queue.fail(task.task_id, "something broke")
        completed = queue.get_completed()
        assert len(completed) == 1
        assert completed[0].status == TaskStatus.FAILED

    def test_peek(self) -> None:
        queue = TaskQueue()
        assert queue.peek() is None
        task = BridgeTask(name="first", priority=TaskPriority.URGENT)
        queue.enqueue(task)
        assert queue.peek() is task

    def test_cancel(self) -> None:
        queue = TaskQueue()
        task = BridgeTask(name="cancel-me")
        queue.enqueue(task)
        assert queue.cancel(task.task_id) is True
        assert queue.cancel("nonexistent") is False
        assert queue.size == 0

    def test_getters(self) -> None:
        queue = TaskQueue()
        assert queue.get_pending() == []
        assert queue.get_completed() == []
        task = BridgeTask(name="t", source_device="src")
        queue.enqueue(task)
        queue.complete(task.task_id, {})
        results = queue.get_by_source("src")
        assert len(results) == 1
