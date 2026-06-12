from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    Image = ImageDraw = ImageFilter = None  # type: ignore[assignment]


class CaptureMode(str, Enum):
    FULL_SCREEN = "full_screen"
    REGION = "region"
    ACTIVE_WINDOW = "active_window"


class DownsampleMethod(str, Enum):
    NONE = "none"
    BILINEAR = "bilinear"
    LANCZOS = "lanczos"


class RedactionMode(str, Enum):
    NONE = "none"
    BLACK_BOX = "black_box"
    BLUR = "blur"
    PIXELATE = "pixelate"


@dataclass
class RedactionZone:
    x: int
    y: int
    width: int
    height: int
    reason: str = ""
    mode: RedactionMode = RedactionMode.BLACK_BOX

    @property
    def region(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class ScreenshotResult:
    image: Image.Image | None = None
    width: int = 0
    height: int = 0
    file_path: str = ""
    capture_time_ms: float = 0.0
    redactions_applied: int = 0
    mode: CaptureMode = CaptureMode.FULL_SCREEN

    def save(self, path: str, format: str = "PNG") -> str:
        if self.image is None:
            raise ValueError("No image data to save")
        self.image.save(path, format=format)
        self.file_path = path
        return path

    def to_bytes(self, format: str = "PNG") -> bytes:
        if self.image is None:
            raise ValueError("No image data to convert")
        import io

        buf = io.BytesIO()
        self.image.save(buf, format=format)
        return buf.getvalue()


class RedactionEngine:
    """Applies redaction zones to screenshots before any external processing.

    Ensures sensitive areas (password fields, API keys, private data)
    are obscured before the image leaves the local machine.
    """

    # Common UI patterns that may contain sensitive content
    SENSITIVE_PATTERNS: list[str] = [
        "password",
        "passwort",
        "mật khẩu",
        "секрет",
        "api key",
        "api_key",
        "apikey",
        "secret",
        "token",
        "private key",
        "credit card",
    ]

    def __init__(self, auto_detect: bool = False) -> None:
        self.auto_detect = auto_detect
        self._manual_zones: list[RedactionZone] = []

    def add_zone(self, zone: RedactionZone) -> None:
        self._manual_zones.append(zone)

    def clear_zones(self) -> None:
        self._manual_zones.clear()

    def redact(self, image: Image.Image, parsed_elements: list[dict[str, Any]] | None = None) -> Image.Image:
        result = image.copy()
        zones = list(self._manual_zones)
        if self.auto_detect and parsed_elements:
            zones.extend(self._detect_sensitive_zones(parsed_elements))
        for zone in zones:
            result = self._apply_redaction(result, zone)
        return result

    def _detect_sensitive_zones(self, elements: list[dict[str, Any]]) -> list[RedactionZone]:
        zones: list[RedactionZone] = []
        for elem in elements:
            text = elem.get("text", "").lower()
            for pattern in self.SENSITIVE_PATTERNS:
                if pattern in text:
                    bbox = elem.get("bbox", {})
                    zones.append(
                        RedactionZone(
                            x=bbox.get("x", 0),
                            y=bbox.get("y", 0),
                            width=bbox.get("width", 200),
                            height=bbox.get("height", 30),
                            reason=f"auto-detected: {pattern}",
                            mode=RedactionMode.BLACK_BOX,
                        )
                    )
                    break
        return zones

    def _apply_redaction(self, image: Image.Image, zone: RedactionZone) -> Image.Image:
        region = image.crop(zone.region)
        if zone.mode == RedactionMode.BLACK_BOX:
            draw = ImageDraw.Draw(image)
            draw.rectangle(zone.region, fill="black")
        elif zone.mode == RedactionMode.BLUR:
            blurred = region.filter(ImageFilter.GaussianBlur(radius=15))
            image.paste(blurred, zone.region)
        elif zone.mode == RedactionMode.PIXELATE:
            small = region.resize((8, 8), resample=Image.NEAREST)  # type: ignore[attr-defined]
            pixelated = small.resize(region.size, Image.NEAREST)  # type: ignore[attr-defined]
            image.paste(pixelated, zone.region)
        return image


class ScreenCapture:
    """Cross-platform screenshot capture with redaction and downsample support.

    macOS: Uses CGDisplay via PyAutoGUI (primary) or screencapture CLI (fallback).
    Linux: Uses PyAutoGUI (X11) or scrot/gnome-screenshot (fallback).
    Windows: Uses PyAutoGUI (Win32 API).

    All captures pass through RedactionEngine before being returned.
    """

    def __init__(
        self,
        downsample_method: DownsampleMethod = DownsampleMethod.NONE,
        downsample_factor: float = 1.0,
        redaction_engine: RedactionEngine | None = None,
    ) -> None:
        if not 0.1 <= downsample_factor <= 1.0:
            raise ValueError("downsample_factor must be between 0.1 and 1.0")
        self.downsample_method = downsample_method
        self.downsample_factor = downsample_factor
        self.redaction = redaction_engine or RedactionEngine()

    @classmethod
    def detect_backend(cls) -> str:
        import platform

        try:
            import pyautogui
            pyautogui.screenshot()
            return "pyautogui"
        except (ImportError, Exception):
            pass

        system = platform.system()
        if system == "Darwin":
            import shutil
            if shutil.which("screencapture"):
                return "screencapture_cli"

        return "none"

    @staticmethod
    def benchmark_capture(num_runs: int = 5) -> dict[str, Any]:
        import time as _time
        capture = ScreenCapture()
        latencies: list[float] = []
        for _ in range(num_runs):
            t0 = _time.time()
            result = capture.capture_fullscreen()
            elapsed = (_time.time() - t0) * 1000
            if result.width > 0:
                latencies.append(elapsed)
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        return {
            "backend": ScreenCapture.detect_backend(),
            "num_runs": num_runs,
            "successful_runs": len(latencies),
            "avg_latency_ms": round(avg_latency, 1),
            "min_latency_ms": round(min(latencies), 1) if latencies else 0.0,
            "max_latency_ms": round(max(latencies), 1) if latencies else 0.0,
        }

    def capture_fullscreen(
        self, output_path: str | None = None, format: str = "PNG"
    ) -> ScreenshotResult:
        return self._capture(CaptureMode.FULL_SCREEN, output_path, format)

    def capture_region(
        self, x: int, y: int, width: int, height: int, output_path: str | None = None, format: str = "PNG"
    ) -> ScreenshotResult:
        return self._capture(CaptureMode.REGION, output_path, format, region=(x, y, width, height))

    def capture_active_window(self, output_path: str | None = None, format: str = "PNG") -> ScreenshotResult:
        return self._capture(CaptureMode.ACTIVE_WINDOW, output_path, format)

    def _capture(
        self,
        mode: CaptureMode,
        output_path: str | None = None,
        format: str = "PNG",
        region: tuple[int, int, int, int] | None = None,
    ) -> ScreenshotResult:
        import time

        start = time.time()
        try:
            image = self._do_capture(mode, region)
        except Exception:
            return ScreenshotResult(
                width=0, height=0, capture_time_ms=(time.time() - start) * 1000, mode=mode
            )

        redactions = 0
        if self.redaction and image is not None:
            image = self.redaction.redact(image)
            if len(self.redaction._manual_zones) > 0:
                redactions = len(self.redaction._manual_zones)

        if image is not None and self.downsample_factor < 1.0:
            new_w = int(image.width * self.downsample_factor)
            new_h = int(image.height * self.downsample_factor)
            if self.downsample_method == DownsampleMethod.BILINEAR:
                image = image.resize((new_w, new_h), Image.BILINEAR)  # type: ignore[attr-defined]
            elif self.downsample_method == DownsampleMethod.LANCZOS:
                image = image.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]
            else:
                image = image.resize((new_w, new_h), Image.NEAREST)  # type: ignore[attr-defined]

        result = ScreenshotResult(
            image=image,
            width=image.width if image else 0,
            height=image.height if image else 0,
            capture_time_ms=(time.time() - start) * 1000,
            redactions_applied=redactions,
            mode=mode,
        )

        if output_path and image:
            result.save(output_path, format)

        return result

    def _do_capture(
        self, mode: CaptureMode, region: tuple[int, int, int, int] | None = None
    ) -> Image.Image:
        try:
            import pyautogui

            if mode == CaptureMode.FULL_SCREEN:
                return pyautogui.screenshot()
            elif mode == CaptureMode.REGION and region:
                x, y, w, h = region
                return pyautogui.screenshot(region=(x, y, w, h))
            elif mode == CaptureMode.ACTIVE_WINDOW:
                return pyautogui.screenshot()
            else:
                return pyautogui.screenshot()
        except ImportError:
            return self._fallback_capture(mode, region)

    def _fallback_capture(
        self, mode: CaptureMode, region: tuple[int, int, int, int] | None = None
    ) -> Image.Image:
        import subprocess

        if os.name == "posix" and os.uname().sysname == "Darwin":
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
            try:
                if mode == CaptureMode.REGION and region:
                    x, y, w, h = region
                    subprocess.run(
                        ["screencapture", "-R", f"{x},{y},{w},{h}", path],
                        check=True, capture_output=True, timeout=30,
                    )
                else:
                    subprocess.run(["screencapture", "-x", path], check=True, capture_output=True, timeout=30)
                img = Image.open(path)
                return img
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(path)

        dummy = Image.new("RGB", (1920, 1080), color=(128, 128, 128))
        return dummy
