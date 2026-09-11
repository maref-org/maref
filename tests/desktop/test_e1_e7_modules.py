"""E1-E7 tests: mobile_bridge, context_isolation, browser_controller, file_watcher, MCP InProcess."""

from __future__ import annotations

import base64
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

from maref.desktop.browser_controller import (
    BrowserAction,
    BrowserController,
    BrowserResult,
    BrowserType,
)
from maref.desktop.context_isolation import (
    ContextIsolation,
    SubAgentSpawner,
    SubAgentSummary,
)
from maref.desktop.file_watcher import (
    FileEvent,
    FileEventType,
    FileWatcher,
)
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
from maref.integration.mcp_transport import (
    InProcessTransport,
    JSONRPCRequest,
    JSONRPCResponse,
)


class TestDeviceInfo:
    def test_create_and_to_dict(self):
        device = DeviceInfo(
            device_id="phone-001",
            name="Frankie's Z Flip3",
            device_type=DeviceType.MOBILE,
            platform=DevicePlatform.ANDROID,
            host="192.168.1.100",
            port=9090,
            capabilities=["adb", "screenshot", "task_dispatch"],
        )
        d = device.to_dict()
        assert d["device_id"] == "phone-001"
        assert d["device_type"] == "mobile"
        assert d["platform"] == "android"
        assert "adb" in d["capabilities"]

    def test_from_dict(self):
        data = {
            "device_id": "desk-001",
            "name": "Mac Studio",
            "device_type": "desktop",
            "platform": "macos",
            "host": "127.0.0.1",
            "port": 8080,
        }
        device = DeviceInfo.from_dict(data)
        assert device.device_id == "desk-001"
        assert device.host == "127.0.0.1"

    def test_fingerprint(self):
        d1 = DeviceInfo(
            device_id="a", name="Mac", platform=DevicePlatform.MACOS, host="1.2.3.4", port=80
        )
        d2 = DeviceInfo(
            device_id="a", name="Mac", platform=DevicePlatform.MACOS, host="1.2.3.4", port=80
        )
        assert d1.fingerprint == d2.fingerprint

    def test_default_values(self):
        device = DeviceInfo(device_id="test", name="test")
        assert device.trust_score == 1.0
        assert device.is_online is True


class TestDeviceDiscovery:
    def test_local_device(self):
        discovery = DeviceDiscovery(device_id="test-agent", port=9999)
        assert discovery.local_device.device_id == "test-agent"
        assert discovery.local_device.port == 9999

    def test_register_and_discover(self):
        discovery = DeviceDiscovery()
        phone = DeviceInfo(device_id="phone-1", name="Phone", device_type=DeviceType.MOBILE)
        discovery.register_device(phone)
        assert len(discovery.discover()) == 1

    def test_discover_by_type(self):
        discovery = DeviceDiscovery()
        discovery.register_device(
            DeviceInfo(device_id="d1", name="Desktop", device_type=DeviceType.DESKTOP)
        )
        discovery.register_device(
            DeviceInfo(device_id="p1", name="Phone", device_type=DeviceType.MOBILE)
        )
        assert len(discovery.discover_by_type(DeviceType.MOBILE)) == 1
        assert len(discovery.discover_by_type(DeviceType.DESKTOP)) == 1

    def test_discover_by_capability(self):
        discovery = DeviceDiscovery()
        d1 = DeviceInfo(device_id="d1", name="D1", capabilities=["adb", "ssh"])
        d2 = DeviceInfo(device_id="d2", name="D2", capabilities=["http"])
        discovery.register_device(d1)
        discovery.register_device(d2)
        assert len(discovery.discover_by_capability("adb")) == 1

    def test_unregister(self):
        discovery = DeviceDiscovery()
        discovery.register_device(DeviceInfo(device_id="temp", name="Temp"))
        discovery.unregister_device("temp")
        assert len(discovery.discover()) == 0

    def test_get_device(self):
        discovery = DeviceDiscovery()
        device = DeviceInfo(device_id="specific", name="Specific")
        discovery.register_device(device)
        assert discovery.get_device("specific") is not None
        assert discovery.get_device("nonexistent") is None

    def test_online_check(self):
        discovery = DeviceDiscovery()
        discovery.register_device(
            DeviceInfo(device_id="test", name="Test", host="127.0.0.1", port=9876)
        )
        status = discovery.check_online(timeout=0.5)
        assert "test" in status


class TestTaskQueue:
    def test_enqueue_dequeue(self):
        queue = TaskQueue()
        task = BridgeTask(name="test", source_device="phone", target_device="desktop")
        assert queue.enqueue(task)
        assert queue.size == 1
        dequeued = queue.dequeue()
        assert dequeued is not None
        assert dequeued.name == "test"

    def test_priority_ordering(self):
        queue = TaskQueue()
        t_low = BridgeTask(name="low", priority=TaskPriority.LOW)
        t_high = BridgeTask(name="high", priority=TaskPriority.HIGH)
        t_urgent = BridgeTask(name="urgent", priority=TaskPriority.URGENT)
        queue.enqueue(t_low)
        queue.enqueue(t_high)
        queue.enqueue(t_urgent)
        assert queue.dequeue().name == "urgent"
        assert queue.dequeue().name == "high"
        assert queue.dequeue().name == "low"

    def test_idempotency(self):
        queue = TaskQueue()
        task1 = BridgeTask(name="t1", idempotency_key="key-001")
        task2 = BridgeTask(name="t2", idempotency_key="key-001")
        assert queue.enqueue(task1)
        assert not queue.enqueue(task2)
        assert queue.size == 1

    def test_complete_task(self):
        queue = TaskQueue()
        task = BridgeTask(name="test")
        queue.enqueue(task)
        queue.complete(task.task_id, {"result": "ok"})
        assert len(queue.get_completed()) == 1
        assert queue.get_completed()[0].status == TaskStatus.COMPLETED

    def test_fail_task(self):
        queue = TaskQueue()
        task = BridgeTask(name="test")
        queue.enqueue(task)
        queue.fail(task.task_id, "timeout")
        assert len(queue.get_completed()) == 1
        assert queue.get_completed()[0].status == TaskStatus.FAILED

    def test_cancel_task(self):
        queue = TaskQueue()
        task = BridgeTask(name="test")
        queue.enqueue(task)
        assert queue.cancel(task.task_id)
        assert queue.size == 0

    def test_get_by_source(self):
        queue = TaskQueue()
        t1 = BridgeTask(name="t1", source_device="phone-a", target_device="desktop")
        t2 = BridgeTask(name="t2", source_device="phone-b", target_device="desktop")
        queue.enqueue(t1)
        queue.enqueue(t2)
        assert len(queue.get_by_source("phone-a")) == 1

    def test_max_queue_size(self):
        queue = TaskQueue(max_queue_size=2)
        assert queue.enqueue(BridgeTask(name="1"))
        assert queue.enqueue(BridgeTask(name="2"))
        assert not queue.enqueue(BridgeTask(name="3"))


class TestSessionManager:
    def test_create_session(self):
        sm = SessionManager()
        sid = sm.create_session("phone-1", "desktop-1")
        assert sm.get_session(sid) is not None
        assert sm.get_session(sid)["active"]

    def test_close_session(self):
        sm = SessionManager()
        sid = sm.create_session("p1", "d1")
        assert sm.close_session(sid)
        assert not sm.get_session(sid)["active"]

    def test_find_by_source(self):
        sm = SessionManager()
        sm.create_session("phone-a", "desktop-x")
        sm.create_session("phone-a", "desktop-y")
        sm.create_session("phone-b", "desktop-z")
        sessions = sm.find_sessions_by_source("phone-a")
        assert len(sessions) == 2

    def test_find_by_target(self):
        sm = SessionManager()
        sm.create_session("phone-x", "desktop-main")
        sm.create_session("phone-y", "desktop-main")
        assert len(sm.find_sessions_by_target("desktop-main")) == 2

    def test_device_pairs(self):
        sm = SessionManager()
        sm.create_session("p1", "d1")
        sm.create_session("p1", "d2")
        pairs = sm.get_device_pairs()
        assert len(pairs) == 2

    def test_session_queue_isolation(self):
        sm = SessionManager()
        sid1 = sm.create_session("p1", "d1")
        sid2 = sm.create_session("p1", "d2")

        q1 = sm.get_queue_for_session(sid1)
        q2 = sm.get_queue_for_session(sid2)
        assert q1 is not None
        assert q2 is not None

        q1.enqueue(BridgeTask(name="task-for-d1"))
        q2.enqueue(BridgeTask(name="task-for-d2"))
        assert q1.size == 1
        assert q2.size == 1


class TestMobileBridge:
    def test_register_and_topology(self):
        bridge = MobileBridge()
        bridge.register_mobile_device(
            DeviceInfo(
                device_id="phone-1",
                name="Phone",
                device_type=DeviceType.MOBILE,
                platform=DevicePlatform.ANDROID,
            )
        )
        topo = bridge.get_device_topology()
        assert len(topo["discovered"]) == 1
        assert topo["device_pairs"] == []

    def test_create_session_and_dispatch(self):
        bridge = MobileBridge()
        bridge.register_mobile_device(
            DeviceInfo(device_id="phone-1", name="Phone", device_type=DeviceType.MOBILE)
        )
        bridge.create_bridge_session("phone-1", bridge.device_id)

        task = bridge.dispatch_task(
            source_device="phone-1",
            target_device=bridge.device_id,
            task_name="Open Finder",
            payload={"app": "Finder", "action": "open"},
            priority=TaskPriority.HIGH,
        )
        assert task.name == "Open Finder"
        assert task.priority == TaskPriority.HIGH

        topo = bridge.get_device_topology()
        assert topo["pending_tasks"] == 1
        assert topo["active_sessions"] == 1

    def test_complete_task(self):
        bridge = MobileBridge()
        bridge.register_mobile_device(
            DeviceInfo(device_id="phone-1", name="Phone", device_type=DeviceType.MOBILE)
        )
        task = bridge.dispatch_task("phone-1", bridge.device_id, "Test", {})
        bridge.complete_task(task.task_id, {"result": "success"})
        assert bridge.get_device_topology()["pending_tasks"] == 0

    def test_fail_task(self):
        bridge = MobileBridge()
        bridge.register_mobile_device(
            DeviceInfo(device_id="phone-1", name="Phone", device_type=DeviceType.MOBILE)
        )
        task = bridge.dispatch_task("phone-1", bridge.device_id, "Test", {})
        bridge.fail_task(task.task_id, "Network error")
        assert bridge.get_device_topology()["pending_tasks"] == 0

    def test_event_log(self):
        bridge = MobileBridge()
        bridge.register_mobile_device(
            DeviceInfo(device_id="phone-1", name="Phone", device_type=DeviceType.MOBILE)
        )
        bridge.create_bridge_session("phone-1", bridge.device_id)
        assert len(bridge.get_event_log()) == 2

    def test_topology_multiple_devices(self):
        bridge = MobileBridge()
        bridge.register_mobile_device(
            DeviceInfo(device_id="p1", name="Phone1", device_type=DeviceType.MOBILE)
        )
        bridge.register_mobile_device(
            DeviceInfo(device_id="p2", name="Phone2", device_type=DeviceType.MOBILE)
        )
        bridge.create_bridge_session("p1", bridge.device_id)
        bridge.create_bridge_session("p2", bridge.device_id)

        topo = bridge.get_device_topology()
        assert len(topo["discovered"]) == 2
        assert topo["active_sessions"] == 2
        assert len(topo["device_pairs"]) == 2


class TestContextIsolation:
    def test_snapshot(self):
        ci = ContextIsolation()
        snapshot = ci.snapshot("iso-1", {"agent_id": "parent", "task": "explore"})
        assert snapshot.parent_id == "parent"
        assert snapshot.context_size > 0

    def test_isolate_filters_keys(self):
        ci = ContextIsolation()
        ci.snapshot("iso-2", {"agent_id": "p", "a": 1, "b": 2, "c": 3})
        filtered = ci.isolate("iso-2", ["a", "c"])
        assert filtered is not None
        assert "a" in filtered.filtered_context
        assert "b" not in filtered.filtered_context

    def test_token_savings_estimate(self):
        ci = ContextIsolation()
        savings = ci.estimate_token_savings(50000, 2000)
        assert savings > 0.9

    def test_merge_summary(self):
        ci = ContextIsolation()
        ci.snapshot("iso-3", {"agent_id": "p", "data": "x" * 1000})
        summary = SubAgentSummary(
            isolation_id="iso-3",
            findings=["Found X", "Found Y"],
            files_explored=["/tmp/a.txt"],
            confidence=0.85,
        )
        ci.merge_summary("iso-3", summary)
        snapshot = ci._isolations.get("iso-3")
        assert snapshot is not None
        assert snapshot.token_savings_pct > 0

    def test_cleanup(self):
        ci = ContextIsolation()
        ci.snapshot("iso-4", {"agent_id": "p"})
        ci.cleanup("iso-4")
        assert "iso-4" not in ci._isolations


class TestSubAgentSpawner:
    def test_spawn_and_complete(self):
        spawner = SubAgentSpawner()
        iso_id = spawner.spawn("parent-1", "Explore /tmp", {"data": "context"}, ["data"])
        summary = spawner.complete(
            iso_id,
            findings=["Found file A"],
            files_explored=["/tmp/a.txt"],
            confidence=0.9,
        )
        assert summary.findings == ["Found file A"]
        assert summary.confidence == 0.9

    def test_token_savings(self):
        spawner = SubAgentSpawner()
        iso_id = spawner.spawn("parent-1", "Explore large context", {"data": "x" * 5000}, ["data"])
        spawner.complete(iso_id, findings=["short summary"], files_explored=[])
        savings = spawner.get_token_savings(iso_id)
        assert savings > 90.0

    def test_get_summary(self):
        spawner = SubAgentSpawner()
        iso_id = spawner.spawn("p1", "test", {}, [])
        spawner.complete(iso_id, ["f1"], [])
        summary = spawner.get_summary(iso_id)
        assert summary is not None
        assert summary.findings == ["f1"]

    def test_cleanup_removes(self):
        spawner = SubAgentSpawner()
        iso_id = spawner.spawn("p1", "clean", {}, [])
        spawner.cleanup(iso_id)
        assert spawner.get_summary(iso_id) is None

    def test_active_count(self):
        spawner = SubAgentSpawner()
        spawner.spawn("p1", "task1", {}, [])
        spawner.spawn("p1", "task2", {}, [])
        assert spawner.get_active_count() == 2
        iso3 = spawner.spawn("p1", "task3", {}, [])
        spawner.complete(iso3, [], [])
        assert spawner.get_active_count() == 2

    def test_sub_agent_summary_to_dict(self):
        summary = SubAgentSummary(
            isolation_id="iso-1",
            findings=["F1"],
            files_explored=["/tmp/a.txt"],
            confidence=0.95,
        )
        d = summary.to_dict()
        assert d["findings"] == ["F1"]
        assert d["confidence"] == 0.95

    def test_sub_agent_summary_from_dict(self):
        data = {"isolation_id": "iso-x", "findings": ["F"], "files_explored": [], "confidence": 0.5}
        summary = SubAgentSummary.from_dict(data)
        assert summary.isolation_id == "iso-x"

    def test_context_snapshot_to_dict(self):
        ci = ContextIsolation()
        ci.snapshot("iso-5", {"agent_id": "p"})
        snapshot = ci._isolations["iso-5"]
        ci.merge_summary("iso-5", SubAgentSummary(isolation_id="iso-5", findings=["f1"]))
        d = snapshot.to_dict()
        assert d["isolation_id"] == "iso-5"
        assert d["summary"] is not None


class TestBrowserController:
    def test_init_defaults(self):
        bc = BrowserController()
        assert bc.dry_run is False
        assert bc.browser_type == BrowserType.CHROMIUM

    def test_is_safe_domain(self):
        bc = BrowserController()
        assert bc.is_safe_domain("https://github.com/maref/repo")
        assert bc.is_safe_domain("https://docs.python.org/3/")
        assert not bc.is_safe_domain("https://evil-site.com")

    def test_navigate_dry_run(self):
        bc = BrowserController(dry_run=True)
        result = bc.navigate("https://docs.python.org")
        assert result.success
        assert "[DRY RUN]" in result.text

    def test_navigate_unsafe_domain(self):
        bc = BrowserController(dry_run=True)
        result = bc.navigate("https://malware.com")
        assert not result.success
        assert "Domain not in safe list" in result.error

    def test_click_dry_run(self):
        bc = BrowserController(dry_run=True)
        result = bc.click("#submit-btn")
        assert result.success
        assert "[DRY RUN]" in result.text

    def test_type_text_dry_run(self):
        bc = BrowserController(dry_run=True)
        result = bc.type_text("#search", "hello")
        assert result.success

    def test_extract_text_dry_run(self):
        bc = BrowserController(dry_run=True)
        result = bc.extract_text()
        assert result.success

    def test_extract_links_dry_run(self):
        bc = BrowserController(dry_run=True)
        result = bc.extract_links()
        assert result.success
        assert len(result.links) > 0

    def test_screenshot_dry_run(self):
        bc = BrowserController(dry_run=True)
        result = bc.screenshot()
        assert result.success

    def test_execute_js_safe_dry_run(self):
        bc = BrowserController(dry_run=True)
        result = bc.execute_js("document.title")
        assert result.success

    def test_execute_js_dangerous_blocked(self):
        bc = BrowserController(dry_run=True)
        result = bc.execute_js("fetch('https://leak.com')")
        assert not result.success
        assert "Blocked" in result.error

    def test_operation_log(self):
        bc = BrowserController(dry_run=True)
        bc.navigate("https://docs.python.org")
        bc.click("#submit")
        assert len(bc.get_operation_log()) == 2

    def test_result_to_dict(self):
        result = BrowserResult(
            success=True, action=BrowserAction.NAVIGATE, url="https://example.com"
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["url"] == "https://example.com"

    # --- Real (non-dry-run) _do_* method tests ---

    def test_do_click_no_page(self):
        bc = BrowserController(dry_run=False)
        bc._ensure_session = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = bc.click("#btn")
        assert not result.success
        assert "No active page" in result.error

    def test_do_click_success(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        result = bc.click("#btn")
        assert result.success
        bc._page.click.assert_called_once_with("#btn", timeout=5000)

    def test_do_click_error(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        bc._page.click.side_effect = Exception("element not found")
        result = bc.click("#btn")
        assert not result.success
        assert "element not found" in result.error

    def test_do_type_no_page(self):
        bc = BrowserController(dry_run=False)
        bc._ensure_session = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = bc.type_text("#input", "hello")
        assert not result.success
        assert "No active page" in result.error

    def test_do_type_fill(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        locator_mock = MagicMock()
        locator_mock.count = AsyncMock(return_value=1)
        bc._page.locator = MagicMock(return_value=locator_mock)
        result = bc.type_text("#input", "hello")
        assert result.success
        bc._page.fill.assert_called_once_with("#input", "hello")

    def test_do_type_fallback(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        locator_mock = MagicMock()
        locator_mock.count = AsyncMock(return_value=0)
        bc._page.locator = MagicMock(return_value=locator_mock)
        result = bc.type_text("#input", "hello")
        assert result.success
        bc._page.type.assert_called_once_with("#input", "hello")

    def test_do_type_error(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        locator_mock = MagicMock()
        locator_mock.count = AsyncMock(side_effect=Exception("selector error"))
        bc._page.locator = MagicMock(return_value=locator_mock)
        result = bc.type_text("#input", "hello")
        assert not result.success
        assert "selector error" in result.error

    def test_do_extract_text_no_page(self):
        bc = BrowserController(dry_run=False)
        bc._ensure_session = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = bc.extract_text()
        assert not result.success
        assert "No active page" in result.error

    def test_do_extract_text_success(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        bc._page.evaluate = AsyncMock(return_value="Hello World")
        result = bc.extract_text()
        assert result.success
        assert result.text == "Hello World"

    def test_do_extract_text_error(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        bc._page.evaluate.side_effect = Exception("evaluation failed")
        result = bc.extract_text()
        assert not result.success
        assert "evaluation failed" in result.error

    def test_do_extract_links_no_page(self):
        bc = BrowserController(dry_run=False)
        bc._ensure_session = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = bc.extract_links()
        assert not result.success
        assert "No active page" in result.error

    def test_do_extract_links_success(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        expected = [
            {"href": "https://example.com", "text": "Example"},
            {"href": "https://python.org", "text": "Python"},
        ]
        bc._page.evaluate = AsyncMock(return_value=expected)
        result = bc.extract_links()
        assert result.success
        assert result.links == expected
        assert len(result.links) == 2

    def test_do_extract_links_error(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        bc._page.evaluate.side_effect = Exception("dom error")
        result = bc.extract_links()
        assert not result.success
        assert "dom error" in result.error

    def test_do_screenshot_no_page(self):
        bc = BrowserController(dry_run=False)
        bc._ensure_session = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = bc.screenshot()
        assert not result.success
        assert "No active page" in result.error

    def test_do_screenshot_success(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        png_bytes = b"fake_png_data"
        bc._page.screenshot = AsyncMock(return_value=png_bytes)
        result = bc.screenshot()
        assert result.success
        bc._page.screenshot.assert_called_once_with(full_page=True)
        assert result.text == base64.b64encode(png_bytes).decode("ascii")
        assert result.screenshot_bytes == png_bytes

    def test_do_screenshot_error(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        bc._page.screenshot.side_effect = Exception("screenshot failed")
        result = bc.screenshot()
        assert not result.success
        assert "screenshot failed" in result.error

    def test_do_execute_js_no_page(self):
        bc = BrowserController(dry_run=False)
        bc._ensure_session = AsyncMock(return_value=None)  # type: ignore[method-assign]
        result = bc.execute_js("document.title")
        assert not result.success
        assert "No active page" in result.error

    def test_do_execute_js_success(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        bc._page.evaluate = AsyncMock(return_value="Page Title")
        result = bc.execute_js("document.title")
        assert result.success
        assert result.text == "Page Title"

    def test_do_execute_js_error(self):
        bc = BrowserController(dry_run=False)
        bc._page = AsyncMock()
        bc._page.evaluate.side_effect = Exception("js error")
        result = bc.execute_js("document.title")
        assert not result.success
        assert "js error" in result.error

class TestFileWatcher:
    def test_init_defaults(self):
        fw = FileWatcher()
        assert not fw._watching

    def test_add_watch_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fw = FileWatcher(watch_dirs=[tmpdir])
            assert len(fw._watch_dirs) == 1

    def test_add_blocked_dir(self):
        fw = FileWatcher()
        assert not fw.add_watch_dir("/etc")
        assert not fw.add_watch_dir(os.path.expanduser("~/.ssh"))

    def test_poll_detects_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fw = FileWatcher(watch_dirs=[tmpdir])
            fw.start()
            test_file = os.path.join(tmpdir, "new_file.txt")
            with open(test_file, "w") as f:
                f.write("hello")
            events = fw.poll()
            assert len(events) > 0
            created = [e for e in events if e.event_type == FileEventType.CREATED]
            assert len(created) > 0
            fw.stop()

    def test_poll_detects_modification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "mod_file.txt")
            with open(test_file, "w") as f:
                f.write("initial")

            fw = FileWatcher(watch_dirs=[tmpdir])
            fw.start()
            fw.poll()

            with open(test_file, "w") as f:
                f.write("modified")
            events = fw.poll()
            modified = [e for e in events if e.event_type == FileEventType.MODIFIED]
            assert len(modified) > 0
            fw.stop()

    def test_poll_detects_deletion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "del_file.txt")
            with open(test_file, "w") as f:
                f.write("delete me")

            fw = FileWatcher(watch_dirs=[tmpdir])
            fw.start()
            fw.poll()
            os.unlink(test_file)
            events = fw.poll()
            deleted = [e for e in events if e.event_type == FileEventType.DELETED]
            assert len(deleted) > 0
            fw.stop()

    def test_stop_stops_polling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fw = FileWatcher(watch_dirs=[tmpdir])
            fw.start()
            fw.stop()
            with open(os.path.join(tmpdir, "x.txt"), "w") as f:
                f.write("x")
            events = fw.poll()
            assert len(events) == 0

    def test_event_callback(self):
        events_received = []

        def cb(event: FileEvent) -> None:
            events_received.append(event)

        with tempfile.TemporaryDirectory() as tmpdir:
            fw = FileWatcher(watch_dirs=[tmpdir], event_callback=cb)
            fw.start()
            with open(os.path.join(tmpdir, "cb_file.txt"), "w") as f:
                f.write("data")
            fw.poll()
            assert len(events_received) > 0
            fw.stop()

    def test_get_events_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fw = FileWatcher(watch_dirs=[tmpdir])
            fw.start()
            with open(os.path.join(tmpdir, "f1.txt"), "w") as f:
                f.write("1")
            fw.poll()
            created_events = fw.get_events_by_type(FileEventType.CREATED)
            assert len(created_events) > 0

    def test_remove_watch_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fw = FileWatcher(watch_dirs=[tmpdir])
            assert len(fw._watch_dirs) == 1
            fw.remove_watch_dir(tmpdir)
            assert len(fw._watch_dirs) == 0

    def test_file_event_to_dict(self):
        event = FileEvent(
            event_type=FileEventType.CREATED,
            path="/tmp/test.txt",
            file_size=100,
            is_directory=False,
        )
        d = event.to_dict()
        assert d["event_type"] == "created"
        assert d["path"] == "/tmp/test.txt"
        assert d["file_size"] == 100


class TestInProcessTransport:
    def test_connect(self):
        transport = InProcessTransport()
        transport.connect()
        assert transport._state.value == "connected"

    def test_send_request(self):
        transport = InProcessTransport()
        transport.connect()
        request = JSONRPCRequest(method="tools/list", id=1)
        response = transport.send(request)
        assert response.result is not None
        assert response.result["via"] == "inprocess"

    def test_send_disconnected(self):
        transport = InProcessTransport()
        request = JSONRPCRequest(method="test", id=1)
        response = transport.send(request)
        assert response.error is not None
        assert "not connected" in response.error["message"]

    def test_send_async(self):
        transport = InProcessTransport()
        transport.connect()
        request = JSONRPCRequest(method="ping", id=1)
        transport.send_async(request)
        assert len(transport.get_pending_requests()) == 1

    def test_custom_handler(self):
        def handler(request: JSONRPCRequest) -> JSONRPCResponse:
            return JSONRPCResponse(result={"custom": True, "method": request.method}, id=request.id)

        transport = InProcessTransport(message_handler=handler)
        transport.connect()
        response = transport.send(JSONRPCRequest(method="custom.test", id=2))
        assert response.result["custom"] is True

    def test_get_responses(self):
        transport = InProcessTransport()
        transport.connect()
        transport.send(JSONRPCRequest(method="m1", id=1))
        transport.send(JSONRPCRequest(method="m2", id=2))
        assert len(transport.get_responses()) == 2

    def test_clear(self):
        transport = InProcessTransport()
        transport.connect()
        transport.send(JSONRPCRequest(method="m1", id=1))
        transport.clear()
        assert len(transport.get_pending_requests()) == 0
        assert len(transport.get_responses()) == 0


class TestBridgeIntegration:
    """Cross-module integration: mobile bridge + context isolation + desktop agent."""

    def test_mobile_dispatches_to_sub_agent(self):
        bridge = MobileBridge()
        spawner = SubAgentSpawner()

        bridge.register_mobile_device(
            DeviceInfo(device_id="phone-1", name="Phone", device_type=DeviceType.MOBILE)
        )
        bridge.create_bridge_session("phone-1", bridge.device_id)

        task = bridge.dispatch_task(
            "phone-1", bridge.device_id, "Explore Project", {"path": "/tmp/test"}
        )
        iso_id = spawner.spawn(bridge.device_id, task.name, {"task": task.to_dict()}, ["task"])
        summary = spawner.complete(
            iso_id, ["Found test files"], ["/tmp/test/a.txt"], confidence=0.92
        )
        bridge.complete_task(task.task_id, {"summary": summary.to_dict()})

        assert spawner.get_token_savings(iso_id) > 0

    def test_one_phone_multiple_desktop_topology(self):
        bridge = MobileBridge()
        bridge.register_mobile_device(
            DeviceInfo(device_id="phone-1", name="Phone", device_type=DeviceType.MOBILE)
        )
        bridge.create_bridge_session("phone-1", bridge.device_id)
        bridge.dispatch_task("phone-1", bridge.device_id, "Task A", {"action": "screenshot"})
        bridge.dispatch_task("phone-1", bridge.device_id, "Task B", {"action": "parse_ui"})
        topo = bridge.get_device_topology()
        assert topo["pending_tasks"] == 2
        assert topo["active_sessions"] == 1
