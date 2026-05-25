from __future__ import annotations

import platform

from maref.desktop.platform_layer import (
    PlatformCompatibilityMatrix,
    PlatformInputController,
    PlatformScreenCapture,
)
from maref.inference.memory_trust import (
    MemoryCell,
    MemoryThreeTemperature,
    MemoryTier,
    TrustAntiGaming,
)
from maref.serverless_handler import (
    CloudRunHandler,
    LambdaHandler,
    ServerlessEvent,
    ServerlessResponse,
)

# ── Cycle 2: Platform Coverage ────────────────────────────────────

class TestPlatformScreenCapture:
    def test_detects_current_system(self) -> None:
        cap = PlatformScreenCapture()
        info = cap.detect_platform()
        assert "system" in info
        assert "platform" in info
        assert info["system"] in ("Darwin", "Linux", "Windows")

    def test_detects_display_server(self) -> None:
        cap = PlatformScreenCapture()
        ds = cap.detect_display_server()
        assert ds in ("quartz", "x11", "wayland", "dxgi", "unknown")

    def test_screen_info_on_current_platform(self) -> None:
        cap = PlatformScreenCapture()
        info = cap.get_screen_info()
        assert info.width >= 0
        assert info.height >= 0
        assert info.dpi_scale >= 0

    def test_capture_returns_filename(self) -> None:
        cap = PlatformScreenCapture()
        filename = cap.capture()
        assert ".png" in filename


class TestPlatformInputController:
    def test_supported_operations_list(self) -> None:
        pic = PlatformInputController()
        ops = pic.list_supported_operations()
        assert "click" in ops
        assert "type" in ops
        assert len(ops) >= 6

    def test_operation_support_check(self) -> None:
        pic = PlatformInputController()
        assert pic.is_operation_supported("click") is True
        assert pic.is_operation_supported("scroll") is True
        assert pic.is_operation_supported("invalid_op") is False

    def test_platform_driver_name(self) -> None:
        pic = PlatformInputController()
        driver = pic.get_platform_driver()
        assert len(driver) > 0


class TestPlatformCompatibilityMatrix:
    def test_check_all(self) -> None:
        matrix = PlatformCompatibilityMatrix()
        results = matrix.check_all()
        current = platform.system().lower()
        assert current in results

    def test_report_returns_summary(self) -> None:
        matrix = PlatformCompatibilityMatrix()
        report = matrix.report()
        assert "per_os" in report
        assert "summary" in report
        current = platform.system().lower()
        assert current in report["summary"]

    def test_capability_count(self) -> None:
        matrix = PlatformCompatibilityMatrix()
        assert len(matrix.CAPABILITIES) == 15


# ── Cycle 3: Intelligence Enhancement ─────────────────────────────

class TestMemoryThreeTemperature:
    def test_store_hot(self) -> None:
        mem = MemoryThreeTemperature()
        cell = mem.store("key1", "value1", MemoryTier.HOT)
        assert cell.tier == MemoryTier.HOT
        assert cell.value == "value1"

    def test_store_warm(self) -> None:
        mem = MemoryThreeTemperature()
        mem.store("k1", "v1", MemoryTier.WARM, ttl=7200)
        retrieved = mem.retrieve("k1")
        assert retrieved is not None
        assert retrieved.value == "v1"

    def test_store_cold(self) -> None:
        mem = MemoryThreeTemperature()
        mem.store("k2", "v2", MemoryTier.COLD)
        retrieved = mem.retrieve_by_tier("k2", MemoryTier.COLD)
        assert retrieved is not None

    def test_retrieve_missing(self) -> None:
        mem = MemoryThreeTemperature()
        assert mem.retrieve("nonexistent_key") is None

    def test_retrieve_increments_access_count(self) -> None:
        mem = MemoryThreeTemperature()
        mem.store("count_key", "v", MemoryTier.HOT)
        mem.retrieve("count_key")
        mem.retrieve("count_key")
        cell = mem.retrieve("count_key")
        assert cell.access_count >= 3

    def test_clear_tier(self) -> None:
        mem = MemoryThreeTemperature()
        for i in range(5):
            mem.store(f"k{i}", f"v{i}", MemoryTier.HOT)
        assert mem.stats()["hot"] == 5
        cleared = mem.clear_tier(MemoryTier.HOT)
        assert cleared == 5
        assert mem.stats()["hot"] == 0

    def test_stats(self) -> None:
        mem = MemoryThreeTemperature()
        mem.store("h1", "v", MemoryTier.HOT)
        mem.store("w1", "v", MemoryTier.WARM)
        mem.store("c1", "v", MemoryTier.COLD)
        s = mem.stats()
        assert s == {"hot": 1, "warm": 1, "cold": 1}

    def test_memory_cell_expiry(self) -> None:
        cell = MemoryCell(key="tk", value="tv", tier=MemoryTier.HOT, ttl_seconds=0.001)
        import time
        time.sleep(0.01)
        assert cell.is_expired is True


class TestTrustAntiGaming:
    def test_initial_state(self) -> None:
        tag = TrustAntiGaming()
        result = tag.observe(0.8, 0.85)
        assert result["gaming_detected"] is False

    def test_normal_correlation(self) -> None:
        tag = TrustAntiGaming()
        for i in range(60):
            q = 0.7 + (i % 10) * 0.01
            s = 0.7 + (i % 7) * 0.01
            result = tag.observe(q, s)
        assert "correlation" in result

    def test_gaming_detection_positive_correlation(self) -> None:
        tag = TrustAntiGaming(gaming_threshold=0.5)
        for i in range(55):
            tag.observe(0.5 + i * 0.01, 0.5 + i * 0.01)
        result = tag.observe(1.0, 1.0)
        assert result["gaming_detected"] is True

    def test_low_samples_no_detection(self) -> None:
        tag = TrustAntiGaming()
        result = tag.observe(0.5, 0.5)
        assert result["correlation"] is None
        assert result["gaming_detected"] is False

    def test_window_eviction(self) -> None:
        tag = TrustAntiGaming(window_size=10)
        for i in range(30):
            tag.observe(0.5, 0.5)
        assert tag._behavior_history is not None
        assert len(tag._behavior_history) <= 10


# ── Cycle 4 + 5: Serverless + Ecosystem ───────────────────────────

class TestServerlessHandler:
    def test_lambda_handler_cold_start(self) -> None:
        handler = LambdaHandler()
        result = handler.handle({"event_id": "e1", "action": "status"})
        body = __import__("json").loads(result["body"])
        assert body["cold_start"] is True

    def test_lambda_handler_warm_start(self) -> None:
        handler = LambdaHandler()
        handler.handle({"event_id": "e1"})
        result = handler.handle({"event_id": "e2"})
        body = __import__("json").loads(result["body"])
        assert body["cold_start"] is False

    def test_cloud_run_handler(self) -> None:
        handler = CloudRunHandler()
        result = handler.handle({"action": "governance_status"})
        assert result["status"] == "ok"
        assert result["runtime"] == "cloud_run"

    def test_serverless_event_defaults(self) -> None:
        event = ServerlessEvent()
        assert event.event_id == ""
        assert event.action == ""

    def test_serverless_response_to_dict(self) -> None:
        resp = ServerlessResponse(status_code=200, body={"ok": True})
        d = resp.to_dict()
        assert d["statusCode"] == 200
        assert "ok" in d["body"]
