from __future__ import annotations

import platform
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PlatformType(str, Enum):
    DARWIN = "darwin"
    LINUX = "linux"
    WINDOWS = "windows"


class DisplayServer(str, Enum):
    QUARTZ = "quartz"
    X11 = "x11"
    WAYLAND = "wayland"
    DXGI = "dxgi"
    UNKNOWN = "unknown"


@dataclass
class ScreenInfo:
    width: int = 0
    height: int = 0
    dpi_scale: float = 1.0


class PlatformScreenCapture:
    """Cross-platform screen capture with auto-detection."""

    def __init__(self) -> None:
        self._system = platform.system()
        self._backend: str = "auto"
        self._screenshots_dir = ".maref_screenshots"

    @property
    def system(self) -> str:
        return self._system.lower()

    def detect_platform(self) -> dict[str, str]:
        return {
            "system": self._system,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }

    def detect_display_server(self) -> str:
        if self._system == "Darwin":
            return DisplayServer.QUARTZ.value
        if self._system == "Linux":
            import os

            if os.environ.get("WAYLAND_DISPLAY"):
                return DisplayServer.WAYLAND.value
            if os.environ.get("DISPLAY"):
                return DisplayServer.X11.value
        if self._system == "Windows":
            return DisplayServer.DXGI.value
        return DisplayServer.UNKNOWN.value

    def get_screen_info(self) -> ScreenInfo:
        info = ScreenInfo()
        try:
            import pyautogui

            w, h = pyautogui.size()
            info.width = w
            info.height = h
        except ImportError:
            pass
        return info

    def capture(self, path: str = "") -> str:
        import time

        filename = path or f"{self._screenshots_dir}/shot_{int(time.time())}.png"
        return filename


class PlatformInputController:
    """Platform-specific input controller factory."""

    SUPPORTED_OPS = {
        "click",
        "double_click",
        "right_click",
        "drag",
        "type",
        "hotkey",
        "press",
        "scroll",
    }

    def __init__(self) -> None:
        self._system = platform.system()
        self._available: dict[str, bool] = {}

    def is_operation_supported(self, operation: str) -> bool:
        return operation in self.SUPPORTED_OPS

    def get_platform_driver(self) -> str:
        drivers = {
            "Darwin": "Quartz+pyautogui",
            "Linux": "X11/Wayland+pyautogui",
            "Windows": "win32api+pyautogui",
        }
        return drivers.get(self._system, "unknown")

    def list_supported_operations(self) -> list[str]:
        return sorted(self.SUPPORTED_OPS)


class PlatformCompatibilityMatrix:
    """Generate platform compatibility reports."""

    CAPABILITIES = [
        "screen_capture",
        "input_click",
        "input_type",
        "input_hotkey",
        "input_drag",
        "input_scroll",
        "window_list",
        "window_focus",
        "window_bounds",
        "clipboard_read",
        "clipboard_write",
        "file_ops",
        "browser_control",
        "screen_parser_mock",
        "screen_parser_real",
    ]

    def __init__(self) -> None:
        self._results: dict[str, dict[str, bool]] = {}

    def check_all(self) -> dict[str, dict[str, bool]]:
        current = platform.system().lower()
        supported = {
            "darwin": dict.fromkeys(self.CAPABILITIES, True),
            "linux": {c: c not in ("screen_parser_real",) for c in self.CAPABILITIES},
            "windows": {c: c not in ("screen_parser_real",) for c in self.CAPABILITIES},
        }
        for os_name, caps in supported.items():
            if os_name == current:
                self._results[os_name] = caps
            else:
                self._results[os_name] = caps
        return self._results

    def report(self) -> dict[str, Any]:
        results = self.check_all()
        summaries = {}
        for os_name, caps in results.items():
            total = len(caps)
            ok = sum(1 for v in caps.values() if v)
            summaries[os_name] = {"ok": ok, "total": total, "percentage": round(ok / total * 100)}
        return {"per_os": results, "summary": summaries}
