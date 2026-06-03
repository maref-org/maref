from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

Image: Any | None = None
try:
    from PIL import Image as _PILImage  # noqa: N813

    Image = _PILImage
except ImportError:
    pass


def _pixel_value(img: PILImage, x: int, y: int) -> int:
    """Safely extract a single int pixel value from a grayscale PIL image."""
    px = img.getpixel((x, y))
    if isinstance(px, tuple):
        return int(px[0])
    return int(px) if px is not None else 0


class VerificationMethod(str, Enum):
    SCREENSHOT_DIFF = "screenshot_diff"
    ELEMENT_PRESENCE = "element_presence"
    TEXT_MATCH = "text_match"
    WINDOW_STATE = "window_state"
    TIMEOUT_WAIT = "timeout_wait"
    CUSTOM = "custom"


class DiffSeverity(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


@dataclass
class DiffRegion:
    x: int
    y: int
    width: int
    height: int
    severity: DiffSeverity = DiffSeverity.MINOR
    diff_percentage: float = 0.0

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "severity": self.severity.value,
            "diff_percentage": self.diff_percentage,
        }


@dataclass
class VerificationResult:
    passed: bool
    method: VerificationMethod
    details: str = ""
    before_image: PILImage | None = None
    after_image: PILImage | None = None
    diff_image: PILImage | None = None
    diff_percentage: float = 0.0
    diff_regions: list[DiffRegion] | None = None
    retry_count: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "method": self.method.value,
            "details": self.details,
            "diff_percentage": self.diff_percentage,
            "retry_count": self.retry_count,
            "duration_ms": self.duration_ms,
        }


class ScreenshotVerifier:
    """Post-operation verification using screenshot comparison (SSIM-alike).

    Compares before/after screenshots to confirm operations had the
    intended effect. Supports configurable diff thresholds and
    multi-region diff detection.
    """

    def __init__(
        self,
        diff_threshold: float = 0.05,
        pixel_diff_threshold: int = 30,
        min_diff_area: int = 50,
    ) -> None:
        if not 0 < diff_threshold <= 1.0:
            raise ValueError("diff_threshold must be in (0, 1]")
        self.diff_threshold = diff_threshold
        self.pixel_diff_threshold = pixel_diff_threshold
        self.min_diff_area = min_diff_area

    def compare(
        self,
        before: PILImage,
        after: PILImage,
        expected_change_regions: list[DiffRegion] | None = None,
    ) -> VerificationResult:
        start = time.time()
        if before.size != after.size:
            result = VerificationResult(
                passed=False,
                method=VerificationMethod.SCREENSHOT_DIFF,
                details=f"Size mismatch: before={before.size} after={after.size}",
                duration_ms=(time.time() - start) * 1000,
            )
            return result

        before_gray = before.convert("L")
        after_gray = after.convert("L")

        diff_pixels = 0
        total_pixels = before_gray.width * before_gray.height
        diff_img = Image.new("RGB", before.size, color=(0, 0, 0))  # type: ignore[union-attr]

        for y in range(before.height):
            for x in range(before.width):
                delta = abs(_pixel_value(before_gray, x, y) - _pixel_value(after_gray, x, y))
                if delta > self.pixel_diff_threshold:
                    diff_pixels += 1
                    intensity = min(255, delta * 2)
                    diff_img.putpixel((x, y), (intensity, 0, 0))

        diff_pct = diff_pixels / max(total_pixels, 1)

        regions = self._find_diff_regions(before_gray, after_gray)
        passed = diff_pct <= self.diff_threshold

        return VerificationResult(
            passed=passed,
            method=VerificationMethod.SCREENSHOT_DIFF,
            details=f"Diff: {diff_pct * 100:.2f}% ({diff_pixels}/{total_pixels} pixels)",
            before_image=before,
            after_image=after,
            diff_image=diff_img,
            diff_percentage=diff_pct,
            diff_regions=regions,
            duration_ms=(time.time() - start) * 1000,
        )

    def verify_with_retry(
        self,
        capture_before: Callable[[], PILImage],
        execute_action: Callable[[], bool],
        capture_after: Callable[[], PILImage],
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> VerificationResult:
        before = capture_before()
        for attempt in range(max_retries):
            execute_action()
            time.sleep(retry_delay)
            after = capture_after()
            result = self.compare(before, after)
            result.retry_count = attempt
            if result.passed:
                return result
            before = after
        return result

    def _find_diff_regions(self, before: PILImage, after: PILImage) -> list[DiffRegion]:
        if before.size != after.size:
            return []
        regions: list[DiffRegion] = []
        visited: set = set()

        for y in range(before.height):
            for x in range(before.width):
                if (x, y) in visited:
                    continue
                delta = abs(_pixel_value(before, x, y) - _pixel_value(after, x, y))
                if delta > self.pixel_diff_threshold:
                    region = self._flood_fill_region(before, after, x, y, visited)
                    if region.width * region.height >= self.min_diff_area:
                        total = region.width * region.height
                        diff_count = self._count_diff_in_region(before, after, region)
                        region.diff_percentage = diff_count / max(total, 1)
                        if region.diff_percentage > 0.3:
                            region.severity = DiffSeverity.MAJOR
                        elif region.diff_percentage > 0.1:
                            region.severity = DiffSeverity.MODERATE
                        regions.append(region)
        return regions

    def _flood_fill_region(
        self,
        before: PILImage,
        after: PILImage,
        start_x: int,
        start_y: int,
        visited: set,
    ) -> DiffRegion:
        stack = [(start_x, start_y)]
        min_x, min_y = start_x, start_y
        max_x, max_y = start_x, start_y
        w, h = before.width, before.height

        while stack:
            x, y = stack.pop()
            if (x, y) in visited:
                continue
            if x < 0 or x >= w or y < 0 or y >= h:
                continue
            delta = abs(_pixel_value(before, x, y) - _pixel_value(after, x, y))
            if delta <= self.pixel_diff_threshold:
                continue
            visited.add((x, y))
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                stack.append((x + dx, y + dy))

        return DiffRegion(
            x=min_x,
            y=min_y,
            width=max_x - min_x + 1,
            height=max_y - min_y + 1,
            severity=DiffSeverity.MINOR,
        )

    def _count_diff_in_region(self, before: PILImage, after: PILImage, region: DiffRegion) -> int:
        count = 0
        for y in range(region.y, region.y + region.height):
            for x in range(region.x, region.x + region.width):
                if x < before.width and y < before.height:
                    delta = abs(_pixel_value(before, x, y) - _pixel_value(after, x, y))
                    if delta > self.pixel_diff_threshold:
                        count += 1
        return count

    @staticmethod
    def benchmark(image_size: tuple = (1920, 1080)) -> dict:
        import random
        import time as _time

        if Image is None:
            return {"error": "Pillow not available"}
        w, h = image_size
        results: list[float] = []
        for _ in range(5):
            before = Image.new("RGB", (w, h), color=(128, 128, 128))
            after = before.copy()
            for _ in range(50):
                rx = random.randint(0, w - 1)
                ry = random.randint(0, h - 1)
                after.putpixel((rx, ry), (255, 255, 255))
            verifier = ScreenshotVerifier(diff_threshold=0.05)
            t0 = _time.time()
            result = verifier.compare(before, after)
            elapsed = (_time.time() - t0) * 1000
            if result.passed is not None:
                results.append(elapsed)
        avg_ms = sum(results) / len(results) if results else 0.0
        return {
            "image_size": image_size,
            "avg_comparison_ms": round(avg_ms, 1),
            "num_runs": len(results),
        }


class OperationVerifier:
    """High-level operation verification combining screenshot diff + state checks.

    After each desktop operation, verifies the operation had the intended effect
    using a combination of:
    - Screenshot comparison
    - Element presence/absence checking
    - Text matching
    - Window state checking
    """

    def __init__(self, screenshot_verifier: ScreenshotVerifier | None = None) -> None:
        self._screenshot_verifier = screenshot_verifier or ScreenshotVerifier()

    def verify_element_appeared(
        self,
        before_image: PILImage,
        after_image: PILImage,
        expected_region: DiffRegion | None = None,
    ) -> VerificationResult:
        result = self._screenshot_verifier.compare(before_image, after_image)
        if expected_region and result.diff_regions:
            found = any(self._regions_overlap(r, expected_region) for r in result.diff_regions)
            if not found:
                result.passed = False
                result.details += (
                    f" | Expected change at ({expected_region.x},{expected_region.y}) not found"
                )
        return result

    def verify_element_disappeared(
        self,
        before_image: PILImage,
        after_image: PILImage,
        target_region: DiffRegion,
    ) -> VerificationResult:
        result = self._screenshot_verifier.compare(before_image, after_image)
        if result.diff_regions:
            for r in result.diff_regions:
                if self._regions_overlap(r, target_region):
                    result.passed = True
                    result.details += f" | Element disappearance confirmed at ({r.x},{r.y})"
                    return result
            result.passed = False
            result.details += " | Element disappearance not confirmed"
        return result

    def verify_no_unexpected_changes(
        self,
        before_image: PILImage,
        after_image: PILImage,
        expected_ignore_regions: list[DiffRegion] | None = None,
    ) -> VerificationResult:
        result = self._screenshot_verifier.compare(before_image, after_image)
        if result.diff_regions and expected_ignore_regions:
            unexpected = [
                r
                for r in result.diff_regions
                if not any(self._regions_overlap(r, ignore) for ignore in expected_ignore_regions)
            ]
            if unexpected:
                result.passed = False
                result.details += f" | {len(unexpected)} unexpected change regions detected"
        return result

    def _regions_overlap(self, a: DiffRegion, b: DiffRegion) -> bool:
        return (
            a.x < b.x + b.width
            and a.x + a.width > b.x
            and a.y < b.y + b.height
            and a.y + a.height > b.y
        )
