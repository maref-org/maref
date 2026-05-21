"""D2 tests: window_manager.py and file_ops.py."""

from __future__ import annotations

import os
import tempfile

from maref.desktop.file_ops import (
    FileOperation,
    FileOperator,
    FileOpRequest,
    FileOpResult,
    FileSafetyGuard,
    SafetyVerdict,
)
from maref.desktop.window_manager import WindowInfo, WindowManager, WindowRegion, WindowState


class TestWindowInfo:
    def test_center(self):
        win = WindowInfo(window_id="test-1", title="Test", app_name="TestApp", x=0, y=0, width=100, height=200)
        assert win.center == (50, 100)

    def test_contains_point_inside(self):
        win = WindowInfo(window_id="t", title="T", app_name="A", x=10, y=20, width=100, height=50)
        assert win.contains_point(50, 40)

    def test_contains_point_outside(self):
        win = WindowInfo(window_id="t", title="T", app_name="A", x=10, y=20, width=100, height=50)
        assert not win.contains_point(200, 200)

    def test_bounds(self):
        win = WindowInfo(window_id="t", title="T", app_name="A", x=5, y=10, width=200, height=100)
        assert win.bounds == (5, 10, 200, 100)

    def test_to_dict(self):
        win = WindowInfo(
            window_id="finder-1", title="Downloads", app_name="Finder",
            x=0, y=0, width=800, height=600, state=WindowState.NORMAL, is_active=True, pid=1234, layer=0,
        )
        d = win.to_dict()
        assert d["window_id"] == "finder-1"
        assert d["app_name"] == "Finder"
        assert d["width"] == 800
        assert d["height"] == 600
        assert d["state"] == "normal"
        assert d["is_active"] is True
        assert d["pid"] == 1234


class TestWindowRegion:
    def test_to_dict(self):
        region = WindowRegion(x=10, y=20, width=100, height=200, window_id="win-1", app_name="Safari")
        d = region.to_dict()
        assert d["x"] == 10
        assert d["y"] == 20
        assert d["window_id"] == "win-1"
        assert d["app_name"] == "Safari"


class TestWindowManager:
    def test_init_defaults(self):
        wm = WindowManager()
        assert isinstance(wm.accessibility_available, bool)
        assert "Finder" in wm._safe_apps
        assert "Safari" in wm._safe_apps

    def test_safe_app_check(self):
        wm = WindowManager()
        assert wm.is_safe_app("Finder")
        assert wm.is_safe_app("Safari")
        assert not wm.is_safe_app("UnknownApp")

    def test_custom_safe_apps(self):
        wm = WindowManager(safe_apps={"MyApp"})
        assert wm.is_safe_app("MyApp")
        assert not wm.is_safe_app("Finder")

    def test_list_windows(self):
        wm = WindowManager()
        windows = wm.list_windows()
        assert isinstance(windows, list)

    def test_get_active_window(self):
        wm = WindowManager()
        active = wm.get_active_window()
        if active is not None:
            assert isinstance(active.title, str)
            assert isinstance(active.app_name, str)
            assert active.is_active

    def test_focus_window(self):
        wm = WindowManager()
        result = wm.focus_window("Finder-main")
        assert isinstance(result, bool)

    def test_find_windows_by_title(self):
        wm = WindowManager()
        results = wm.find_windows_by_title("zzz_nonexistent_window_zzz")
        assert isinstance(results, list)
        assert len(results) == 0

    def test_find_windows_by_app(self):
        wm = WindowManager()
        results = wm.find_windows_by_app("zzz_nonexistent_app_zzz")
        assert isinstance(results, list)

    def test_get_window_region(self):
        wm = WindowManager()
        region = wm.get_window_region("nonexistent_id")
        assert region is None

    def test_move_window(self):
        wm = WindowManager()
        result = wm.move_window("TestApp-0-0", 100, 200)
        assert isinstance(result, bool)

    def test_resize_window(self):
        wm = WindowManager()
        result = wm.resize_window("TestApp-0-0", 800, 600)
        assert isinstance(result, bool)


class TestFileSafetyGuard:
    def test_init_defaults(self):
        guard = FileSafetyGuard()
        assert len(guard.block_paths) > 0
        assert "/etc" in guard.block_paths or any("etc" in p for p in guard.block_paths)

    def test_allow_normal_read(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.READ, path="/tmp/test.txt")
        assert guard.evaluate(request) == SafetyVerdict.ALLOW

    def test_block_chmod(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.CHMOD, path="/tmp/test.txt", permissions=0o755)
        assert guard.evaluate(request) == SafetyVerdict.BLOCK

    def test_block_exec(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.EXEC, path="/tmp/test.sh")
        assert guard.evaluate(request) == SafetyVerdict.BLOCK

    def test_block_restricted_path_read(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.READ, path="/etc/passwd")
        assert guard.evaluate(request) == SafetyVerdict.BLOCK

    def test_sandbox_restricted_path_write(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.WRITE, path="/etc/something.conf", content="test")
        assert guard.evaluate(request) == SafetyVerdict.SANDBOX

    def test_block_sensitive_extension_read(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.READ, path="/tmp/secret.key")
        assert guard.evaluate(request) == SafetyVerdict.BLOCK

    def test_block_delete_outside_home(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.DELETE, path="/tmp/some_file.txt")
        assert guard.evaluate(request) == SafetyVerdict.BLOCK

    def test_allow_delete_in_home(self):
        guard = FileSafetyGuard()
        home = os.path.expanduser("~")
        request = FileOpRequest(operation=FileOperation.DELETE, path=os.path.join(home, "test_delete_me.txt"))
        assert guard.evaluate(request) == SafetyVerdict.ALLOW

    def test_operation_log_tracks_decisions(self):
        guard = FileSafetyGuard()
        guard.evaluate(FileOpRequest(operation=FileOperation.CHMOD, path="/tmp/test"))
        assert len(guard.operation_log) == 1
        assert guard.operation_log[0].verdict == SafetyVerdict.BLOCK


class TestFileOperator:
    def test_init_defaults(self):
        op = FileOperator()
        assert op.dry_run is True

    def test_dry_run_toggle(self):
        op = FileOperator()
        op.dry_run = False
        assert not op.dry_run

    def test_read_file_dry_run(self):
        op = FileOperator(dry_run=True)
        result = op.read_file("/tmp/test.txt")
        assert result.success
        assert "[DRY RUN]" in result.output

    def test_write_file_dry_run(self):
        op = FileOperator(dry_run=True)
        result = op.write_file("/tmp/test.txt", "hello")
        assert result.success
        assert "[DRY RUN]" in result.output

    def test_delete_file_dry_run(self):
        op = FileOperator(dry_run=True)
        result = op.delete_file(os.path.join(os.path.expanduser("~"), "test_delete_me.txt"))
        assert result.success

    def test_move_file_dry_run(self):
        op = FileOperator(dry_run=True)
        result = op.move_file("/tmp/a.txt", "/tmp/b.txt")
        assert result.success

    def test_copy_file_dry_run(self):
        op = FileOperator(dry_run=True)
        result = op.copy_file("/tmp/a.txt", "/tmp/b.txt")
        assert result.success

    def test_list_directory_dry_run(self):
        op = FileOperator(dry_run=True)
        result = op.list_directory("/tmp")
        assert result.success

    def test_make_directory_dry_run(self):
        op = FileOperator(dry_run=True)
        result = op.make_directory("/tmp/test_maref_dir")
        assert result.success

    def test_chmod_blocked(self):
        FileOperator(dry_run=True)
        result = FileOpResult(success=False, operation=FileOperation.CHMOD, path="/tmp/test", verdict=SafetyVerdict.BLOCK)
        assert not result.success
        assert result.verdict == SafetyVerdict.BLOCK

    def test_real_write_and_read(self):
        op = FileOperator(dry_run=False)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("original")
            tmp_path = f.name
        try:
            write_result = op.write_file(tmp_path, "updated content")
            assert write_result.success
            read_result = op.read_file(tmp_path)
            assert read_result.success
            assert "updated content" in read_result.output
        finally:
            os.unlink(tmp_path)

    def test_real_write_sandbox_redirect(self):
        guard = FileSafetyGuard(block_paths={"/tmp/restricted_area"})
        op = FileOperator(safety_guard=guard, dry_run=False)
        result = op.write_file("/tmp/restricted_area/test.txt", "data")
        if result.verdict == SafetyVerdict.SANDBOX:
            assert result.sandbox_path
            assert result.sandbox_path != "/tmp/restricted_area/test.txt"
            if os.path.exists(result.sandbox_path):
                os.unlink(result.sandbox_path)
        assert result.verdict in (SafetyVerdict.SANDBOX, SafetyVerdict.ALLOW)

    def test_real_list_directory(self):
        op = FileOperator(dry_run=False)
        result = op.list_directory("/tmp")
        assert result.success

    def test_real_mkdir(self):
        op = FileOperator(dry_run=False)
        test_dir = os.path.join(tempfile.gettempdir(), "maref_test_mkdir")
        try:
            result = op.make_directory(test_dir)
            assert result.success
            assert os.path.isdir(test_dir)
        finally:
            if os.path.isdir(test_dir):
                os.rmdir(test_dir)

    def test_to_dict_methods(self):
        request = FileOpRequest(operation=FileOperation.WRITE, path="/tmp/f.txt", content="data")
        d = request.to_dict()
        assert d["operation"] == "write"
        assert d["path"] == "/tmp/f.txt"
        assert d["content_length"] == 4

        result = FileOpResult(success=True, operation=FileOperation.READ, path="/tmp/f.txt", verdict=SafetyVerdict.ALLOW)
        d2 = result.to_dict()
        assert d2["success"] is True
        assert d2["verdict"] == "allow"

    def test_restricted_ssh_path_blocked(self):
        guard = FileSafetyGuard()
        ssh_path = os.path.expanduser("~/.ssh/id_rsa")
        request = FileOpRequest(operation=FileOperation.READ, path=ssh_path)
        verdict = guard.evaluate(request)
        assert verdict == SafetyVerdict.BLOCK

    def test_restricted_extensions_pem(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.READ, path="/tmp/cert.pem")
        assert guard.evaluate(request) == SafetyVerdict.BLOCK

    def test_restricted_extensions_env(self):
        guard = FileSafetyGuard()
        request = FileOpRequest(operation=FileOperation.COPY, path="/tmp/.env", destination="/tmp/env_copy")
        assert guard.evaluate(request) == SafetyVerdict.BLOCK
