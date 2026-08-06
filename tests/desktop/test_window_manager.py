from __future__ import annotations

from maref.desktop.window_manager import (
    WindowInfo,
    WindowManager,
    WindowRegion,
    WindowState,
)


class TestWindowInfo:
    def test_center(self) -> None:
        win = WindowInfo(
            window_id="win-1",
            title="Test Window",
            app_name="Finder",
            x=100, y=100,
            width=800, height=600,
        )
        cx, cy = win.center
        assert cx == 500
        assert cy == 400

    def test_bounds(self) -> None:
        win = WindowInfo(
            window_id="win-1",
            title="Test",
            app_name="Finder",
            x=10, y=20,
            width=100, height=200,
        )
        assert win.bounds == (10, 20, 100, 200)

    def test_contains_point_inside(self) -> None:
        win = WindowInfo(
            window_id="win-1",
            title="Test",
            app_name="Finder",
            x=0, y=0,
            width=100, height=100,
        )
        assert win.contains_point(50, 50)

    def test_contains_point_outside(self) -> None:
        win = WindowInfo(
            window_id="win-1",
            title="Test",
            app_name="Finder",
            x=0, y=0,
            width=100, height=100,
        )
        assert not win.contains_point(200, 200)

    def test_to_dict(self) -> None:
        win = WindowInfo(
            window_id="win-1",
            title="Test",
            app_name="Finder",
            x=10, y=20,
            width=100, height=200,
            state=WindowState.NORMAL,
            is_active=True,
            pid=1234,
            layer=0,
        )
        d = win.to_dict()
        assert d["app_name"] == "Finder"
        assert d["is_active"] is True


class TestWindowRegion:
    def test_to_dict(self) -> None:
        region = WindowRegion(x=10, y=20, width=100, height=200, window_id="win-1", app_name="Finder")
        d = region.to_dict()
        assert d["x"] == 10
        assert d["app_name"] == "Finder"


class TestWindowManager:
    def test_init(self) -> None:
        manager = WindowManager()
        assert "Finder" in manager._safe_apps

    def test_accessibility_property(self) -> None:
        manager = WindowManager()
        assert isinstance(manager.accessibility_available, bool)

    def test_quartz_available_property(self) -> None:
        manager = WindowManager()
        assert isinstance(manager.quartz_available, bool)

    def test_backend_info(self) -> None:
        manager = WindowManager()
        info = manager.backend_info
        assert info["system"] == "Darwin"
        assert "active_backend" in info

    def test_is_safe_app(self) -> None:
        manager = WindowManager()
        assert manager.is_safe_app("Finder")
        assert not manager.is_safe_app("UnknownApp")

    def test_list_windows(self) -> None:
        manager = WindowManager()
        windows = manager.list_windows()
        assert isinstance(windows, list)

    def test_list_windows_with_app_filter(self) -> None:
        manager = WindowManager()
        windows = manager.list_windows(app_filter="Finder")
        assert isinstance(windows, list)

    def test_find_windows_by_title_match(self) -> None:
        manager = WindowManager()
        results = manager.find_windows_by_title("Downloads")
        assert isinstance(results, list)

    def test_find_windows_by_title_nomatch(self) -> None:
        manager = WindowManager()
        results = manager.find_windows_by_title("zzz_nonexistent_window_zzz")
        assert isinstance(results, list)
        assert len(results) == 0

    def test_find_windows_by_app(self) -> None:
        manager = WindowManager()
        results = manager.find_windows_by_app("zzz_nonexistent_app_zzz")
        assert isinstance(results, list)

    def test_get_window_region_none(self) -> None:
        manager = WindowManager()
        region = manager.get_window_region("nonexistent_id")
        assert region is None

    def test_backend_info_keys(self) -> None:
        manager = WindowManager()
        info = manager.backend_info
        assert "system" in info
        assert "active_backend" in info
        assert "accessibility" in info
        assert "quartz_backend" in info

    def test_custom_safe_apps(self) -> None:
        manager = WindowManager(safe_apps={"MyApp"})
        assert manager.is_safe_app("MyApp")
        assert not manager.is_safe_app("Finder")
        assert not manager.is_safe_app("")

    def test_is_safe_app_empty(self) -> None:
        manager = WindowManager()
        assert not manager.is_safe_app("")


class TestWindowManagerSubprocess:
    def test_run_applescript_success(self) -> None:
        import subprocess
        original_run = subprocess.run

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = "mock output"
                stderr = ""
            return MockResult()

        subprocess.run = mock_run
        try:
            manager = WindowManager()
            result = manager._run_applescript("test script")
            assert result == "mock output"
        finally:
            subprocess.run = original_run

    def test_run_applescript_nonzero(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 1
                stdout = ""
                stderr = "error"
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            result = manager._run_applescript("test")
            assert result is None
        finally:
            subprocess.run = original

    def test_run_applescript_timeout(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="osascript", timeout=5)

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            result = manager._run_applescript("test")
            assert result is None
        finally:
            subprocess.run = original

    def test_run_applescript_filenotfound(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            raise FileNotFoundError()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            result = manager._run_applescript("test")
            assert result is None
        finally:
            subprocess.run = original

    def test_get_active_window_found(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = "Finder, Test Window, 100, 200, 800, 600"
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            win = manager.get_active_window()
            assert win is not None
            assert win.app_name == "Finder"
            assert win.title == "Test Window"
            assert win.x == 100
            assert win.y == 200
        finally:
            subprocess.run = original

    def test_get_active_window_none(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = ""
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            win = manager.get_active_window()
            assert win is None
        finally:
            subprocess.run = original

    def test_focus_window_success(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = ""
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            assert manager.focus_window("Finder-100-200")
        finally:
            subprocess.run = original

    def test_focus_window_invalid_id(self) -> None:
        manager = WindowManager()
        result = manager.focus_window("")
        assert not result

    def test_move_window_success(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = ""
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            assert manager.move_window("Finder-0-0", 100, 200)
        finally:
            subprocess.run = original

    def test_move_window_invalid_id(self) -> None:
        manager = WindowManager()
        result = manager.move_window("", 100, 200)
        assert not result

    def test_resize_window_success(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = ""
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            assert manager.resize_window("Finder-0-0", 800, 600)
        finally:
            subprocess.run = original

    def test_resize_window_invalid_id(self) -> None:
        manager = WindowManager()
        result = manager.resize_window("", 800, 600)
        assert not result

    def test_list_via_applescript_parsed(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = (
                    "Finder|Downloads|0|0|800|600|Finder-0-0|||"
                    "Safari|Webpage|100|50|1200|800|Safari-100-50|||"
                )
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            windows = manager._list_via_applescript()
            assert len(windows) == 2
            assert windows[0].app_name == "Finder"
            assert windows[0].title == "Downloads"
            assert windows[1].app_name == "Safari"
        finally:
            subprocess.run = original

    def test_list_via_applescript_empty(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = ""
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            windows = manager._list_via_applescript()
            assert windows == []
        finally:
            subprocess.run = original

    def test_list_via_applescript_app_filter(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = (
                    "Finder|Downloads|0|0|800|600|Finder-0-0|||"
                    "Safari|Webpage|100|50|1200|800|Safari-100-50|||"
                )
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            windows = manager._list_via_applescript(app_filter="Finder")
            assert len(windows) == 1
            assert windows[0].app_name == "Finder"
        finally:
            subprocess.run = original

    def test_list_via_applescript_app_filter_nomatch(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = "Finder|Downloads|0|0|800|600|Finder-0-0|||"
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            windows = manager._list_via_applescript(app_filter="Chrome")
            assert len(windows) == 0
        finally:
            subprocess.run = original

    def test_list_via_applescript_malformed_entry(self) -> None:
        import subprocess

        def mock_run(*args, **kwargs):
            class MockResult:
                returncode = 0
                stdout = "Finder|Downloads|0|0|||"  # too few parts
                stderr = ""
            return MockResult()

        original = subprocess.run
        subprocess.run = mock_run
        try:
            manager = WindowManager()
            windows = manager._list_via_applescript()
            assert len(windows) == 0
        finally:
            subprocess.run = original



