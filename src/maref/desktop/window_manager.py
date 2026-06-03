from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any

_PYOBJC_AVAILABLE = False
try:
    import Quartz  # type: ignore[import-not-found] # noqa: F401

    _PYOBJC_AVAILABLE = True
except ImportError:
    pass


class WindowState(str, Enum):
    NORMAL = "normal"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"
    HIDDEN = "hidden"
    FULLSCREEN = "fullscreen"
    UNKNOWN = "unknown"


@dataclass
class WindowInfo:
    window_id: str
    title: str
    app_name: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    state: WindowState = WindowState.NORMAL
    is_active: bool = False
    pid: int = 0
    layer: int = 0

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def contains_point(self, x: int, y: int) -> bool:
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "title": self.title,
            "app_name": self.app_name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "state": self.state.value,
            "is_active": self.is_active,
            "pid": self.pid,
            "layer": self.layer,
        }


@dataclass
class WindowRegion:
    x: int
    y: int
    width: int
    height: int
    window_id: str = ""
    app_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "window_id": self.window_id,
            "app_name": self.app_name,
        }


class WindowManager:
    """Cross-platform window management with multi-backend support.

    macOS backends (auto-selected in order of preference):
    1. Quartz (pyobjc) — native CoreGraphics window enumeration
    2. AppleScript — osascript-based System Events bridge

    Falls back gracefully when accessibility permissions are not granted.
    """

    SAFE_APPS = {
        "Finder",
        "Safari",
        "Google Chrome",
        "Firefox",
        "Visual Studio Code",
        "Terminal",
        "Notes",
        "Calendar",
        "Preview",
        "TextEdit",
    }

    def __init__(self, safe_apps: set[str] | None = None) -> None:
        self._safe_apps = safe_apps or self.SAFE_APPS
        self._accessibility_available = self._check_accessibility()
        self._quartz_available = _PYOBJC_AVAILABLE
        self._system = platform.system()

    @property
    def accessibility_available(self) -> bool:
        return self._accessibility_available

    @property
    def quartz_available(self) -> bool:
        return self._quartz_available

    @property
    def backend_info(self) -> dict[str, Any]:
        return {
            "system": self._system,
            "accessibility": self._accessibility_available,
            "quartz_backend": self._quartz_available,
            "active_backend": "quartz" if self._quartz_available else "applescript",
        }

    def list_windows(self, app_filter: str | None = None) -> list[WindowInfo]:
        if self._quartz_available and self._system == "Darwin":
            windows = self._list_via_quartz(app_filter)
            if windows:
                return windows
        if self._accessibility_available:
            return self._list_via_applescript(app_filter)
        return self._list_via_quartz(app_filter)

    def get_active_window(self) -> WindowInfo | None:
        script = """
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
            tell process frontApp
                set win to front window
                set winTitle to name of win
                set winPos to position of win
                set winSize to size of win
                return {frontApp, winTitle, item 1 of winPos, item 2 of winPos, item 1 of winSize, item 2 of winSize}
            end tell
        end tell
        """
        result = self._run_applescript(script)
        if result:
            parts = result.split(", ")
            if len(parts) >= 6:
                return WindowInfo(
                    window_id=f"{parts[0]}-active",
                    title=parts[1],
                    app_name=parts[0],
                    x=int(parts[2]),
                    y=int(parts[3]),
                    width=int(parts[4]),
                    height=int(parts[5]),
                    is_active=True,
                    state=WindowState.NORMAL,
                )
        return None

    def focus_window(self, window_id: str) -> bool:
        parts = window_id.split("-", 1)
        if len(parts) >= 1:
            app_name = parts[0]
            script = f"""
            tell application "System Events"
                tell process "{app_name}"
                    set frontmost to true
                end tell
            end tell
            """
            result = self._run_applescript(script)
            return result is not None
        return False

    def move_window(self, window_id: str, x: int, y: int) -> bool:
        parts = window_id.split("-", 1)
        if len(parts) >= 1:
            app_name = parts[0]
            script = f"""
            tell application "System Events"
                tell process "{app_name}"
                    set position of front window to {{{x}, {y}}}
                end tell
            end tell
            """
            result = self._run_applescript(script)
            return result is not None
        return False

    def resize_window(self, window_id: str, width: int, height: int) -> bool:
        parts = window_id.split("-", 1)
        if len(parts) >= 1:
            app_name = parts[0]
            script = f"""
            tell application "System Events"
                tell process "{app_name}"
                    set size of front window to {{{width}, {height}}}
                end tell
            end tell
            """
            result = self._run_applescript(script)
            return result is not None
        return False

    def get_window_region(self, window_id: str) -> WindowRegion | None:
        win = None
        for w in self.list_windows():
            if w.window_id == window_id:
                win = w
                break
        if win is None:
            return None
        return WindowRegion(
            x=win.x,
            y=win.y,
            width=win.width,
            height=win.height,
            window_id=win.window_id,
            app_name=win.app_name,
        )

    def find_windows_by_title(self, title_fragment: str) -> list[WindowInfo]:
        results: list[WindowInfo] = []
        for w in self.list_windows():
            if title_fragment.lower() in w.title.lower():
                results.append(w)
        return results

    def find_windows_by_app(self, app_name: str) -> list[WindowInfo]:
        return self.list_windows(app_filter=app_name)

    def is_safe_app(self, app_name: str) -> bool:
        return app_name in self._safe_apps

    def _list_via_applescript(self, app_filter: str | None = None) -> list[WindowInfo]:
        if app_filter:
            pass

        script = """
        tell application "System Events"
            set winList to every process whose background only is false
            set output to ""
            repeat with proc in winList
                set procName to name of proc
                try
                    set winCount to count of windows of proc
                    if winCount > 0 then
                        set frontWin to front window of proc
                        set winTitle to name of frontWin
                        set winPos to position of frontWin
                        set winSize to size of frontWin
                        set winID to (procName & "-" & (item 1 of winPos as string) & "-" & (item 2 of winPos as string))
                        set output to output & procName & "|" & winTitle & "|" & (item 1 of winPos) & "|" & (item 2 of winPos) & "|" & (item 1 of winSize) & "|" & (item 2 of winSize) & "|" & winID & "|||"
                    end if
                end try
            end repeat
            return output
        end tell
        """
        raw = self._run_applescript(script)
        if not raw:
            return []
        windows: list[WindowInfo] = []
        for entry in raw.split("|||"):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split("|")
            if len(parts) >= 7:
                windows.append(
                    WindowInfo(
                        app_name=parts[0],
                        title=parts[1],
                        x=int(parts[2]) if parts[2].lstrip("-").isdigit() else 0,
                        y=int(parts[3]) if parts[3].lstrip("-").isdigit() else 0,
                        width=int(parts[4]) if parts[4].isdigit() else 0,
                        height=int(parts[5]) if parts[5].isdigit() else 0,
                        window_id=parts[6],
                        state=WindowState.NORMAL,
                    )
                )
        if app_filter:
            windows = [w for w in windows if app_filter.lower() in w.app_name.lower()]
        return windows

    def _list_via_quartz(self, app_filter: str | None = None) -> list[WindowInfo]:
        if not _PYOBJC_AVAILABLE:
            return []
        windows: list[WindowInfo] = []
        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
            )
        except Exception:
            return []

        for entry in window_list or []:
            owner = entry.get(Quartz.kCGWindowOwnerName, "")
            if app_filter and app_filter.lower() not in owner.lower():
                continue

            bounds = entry.get(Quartz.kCGWindowBounds, {})
            windows.append(
                WindowInfo(
                    window_id=str(entry.get(Quartz.kCGWindowNumber, 0)),
                    title=entry.get(Quartz.kCGWindowName, "") or "",
                    app_name=owner,
                    x=int(bounds.get("X", 0)),
                    y=int(bounds.get("Y", 0)),
                    width=int(bounds.get("Width", 0)),
                    height=int(bounds.get("Height", 0)),
                    state=WindowState.NORMAL,
                    is_active=bool(entry.get(Quartz.kCGWindowIsOnscreen, False)),
                    pid=int(entry.get(Quartz.kCGWindowOwnerPID, 0)),
                    layer=int(entry.get(Quartz.kCGWindowLayer, 0)),
                )
            )
        return windows

    def _run_applescript(self, script: str) -> str | None:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def _check_accessibility(self) -> bool:
        test_script = """
        tell application "System Events"
            try
                count of every process
                return "true"
            on error
                return "false"
            end try
        end tell
        """
        result = self._run_applescript(test_script)
        return result == "true"
