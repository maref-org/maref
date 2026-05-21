"""D3 tests: verification.py and clipboard.py."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from maref.desktop.clipboard import (
    ClipboardContentType,
    ClipboardController,
    ClipboardEntry,
    ClipboardSafetyFilter,
)
from maref.desktop.verification import (
    DiffRegion,
    DiffSeverity,
    OperationVerifier,
    ScreenshotVerifier,
    VerificationMethod,
    VerificationResult,
)


def make_image(width: int, height: int, color: tuple = (255, 255, 255)) -> Image.Image:
    return Image.new("RGB", (width, height), color=color)


def draw_rect(img: Image.Image, x: int, y: int, w: int, h: int, color: tuple) -> Image.Image:
    draw = ImageDraw.Draw(img)
    draw.rectangle((x, y, x + w, y + h), fill=color)
    return img


class TestScreenshotVerifier:
    def test_init_defaults(self):
        verifier = ScreenshotVerifier()
        assert verifier.diff_threshold == 0.05
        assert verifier.pixel_diff_threshold == 30
        assert verifier.min_diff_area == 50

    def test_init_invalid_threshold(self):
        with pytest.raises(ValueError, match="diff_threshold"):
            ScreenshotVerifier(diff_threshold=0)

    def test_identical_images(self):
        verifier = ScreenshotVerifier()
        img1 = make_image(100, 100, (100, 100, 100))
        img2 = make_image(100, 100, (100, 100, 100))
        result = verifier.compare(img1, img2)
        assert result.passed
        assert result.diff_percentage == 0.0

    def test_completely_different_images(self):
        verifier = ScreenshotVerifier()
        img1 = make_image(100, 100, (0, 0, 0))
        img2 = make_image(100, 100, (255, 255, 255))
        result = verifier.compare(img1, img2)
        assert not result.passed
        assert result.diff_percentage > 0.9

    def test_minor_change_within_threshold(self):
        verifier = ScreenshotVerifier(diff_threshold=0.1)
        img1 = make_image(100, 100, (128, 128, 128))
        img2 = make_image(100, 100, (128, 128, 128))
        img2.putpixel((0, 0), (200, 200, 200))
        result = verifier.compare(img1, img2)
        assert result.passed

    def test_significant_change_exceeds_threshold(self):
        verifier = ScreenshotVerifier(diff_threshold=0.01)
        img1 = make_image(100, 100, (128, 128, 128))
        img2 = make_image(100, 100, (200, 200, 200))
        result = verifier.compare(img1, img2)
        assert not result.passed

    def test_size_mismatch(self):
        verifier = ScreenshotVerifier()
        img1 = make_image(100, 100)
        img2 = make_image(200, 200)
        result = verifier.compare(img1, img2)
        assert not result.passed
        assert "Size mismatch" in result.details

    def test_diff_image_generated(self):
        verifier = ScreenshotVerifier()
        img1 = make_image(50, 50, (0, 0, 0))
        img2 = make_image(50, 50, (255, 255, 255))
        result = verifier.compare(img1, img2)
        assert result.diff_image is not None
        assert result.diff_image.size == (50, 50)

    def test_diff_regions_detected(self):
        verifier = ScreenshotVerifier(pixel_diff_threshold=30, min_diff_area=10)
        img1 = make_image(100, 100, (100, 100, 100))
        img2 = make_image(100, 100, (100, 100, 100))
        draw_rect(img2, 40, 40, 20, 20, (255, 0, 0))
        result = verifier.compare(img1, img2)
        assert result.diff_regions is not None

    def test_result_to_dict(self):
        result = VerificationResult(
            passed=True,
            method=VerificationMethod.SCREENSHOT_DIFF,
            details="ok",
            diff_percentage=0.02,
        )
        d = result.to_dict()
        assert d["passed"] is True
        assert d["method"] == "screenshot_diff"
        assert d["diff_percentage"] == 0.02


class TestOperationVerifier:
    def test_init(self):
        verifier = OperationVerifier()
        assert verifier._screenshot_verifier is not None

    def test_verify_element_appeared(self):
        verifier = OperationVerifier()
        img1 = make_image(100, 100, (100, 100, 100))
        img2 = make_image(100, 100, (100, 100, 100))
        draw_rect(img2, 40, 40, 20, 20, (0, 255, 0))
        result = verifier.verify_element_appeared(img1, img2)
        assert isinstance(result, VerificationResult)

    def test_verify_element_disappeared(self):
        verifier = OperationVerifier()
        img1 = make_image(100, 100, (100, 100, 100))
        draw_rect(img1, 40, 40, 20, 20, (255, 0, 0))
        img2 = make_image(100, 100, (100, 100, 100))
        region = DiffRegion(x=35, y=35, width=30, height=30)
        result = verifier.verify_element_disappeared(img1, img2, region)
        assert isinstance(result, VerificationResult)

    def test_verify_no_unexpected_changes(self):
        verifier = OperationVerifier()
        img1 = make_image(100, 100, (100, 100, 100))
        img2 = make_image(100, 100, (100, 100, 100))
        result = verifier.verify_no_unexpected_changes(img1, img2)
        assert result.passed


class TestDiffRegion:
    def test_creation(self):
        region = DiffRegion(x=10, y=20, width=30, height=40, severity=DiffSeverity.MAJOR, diff_percentage=0.8)
        assert region.x == 10
        assert region.y == 20
        assert region.severity == DiffSeverity.MAJOR
        assert region.diff_percentage == 0.8

    def test_to_dict(self):
        region = DiffRegion(x=0, y=0, width=50, height=50)
        d = region.to_dict()
        assert d["x"] == 0
        assert d["severity"] == "minor"


class TestClipboardEntry:
    def test_default(self):
        entry = ClipboardEntry(content="hello")
        assert entry.content == "hello"
        assert entry.content_type == ClipboardContentType.TEXT
        assert not entry.is_sensitive

    def test_sensitive_detection_password(self):
        entry = ClipboardEntry(content="my password is hunter2")
        assert entry.is_sensitive

    def test_sensitive_detection_api_key(self):
        entry = ClipboardEntry(content="sk-proj-1234567890abcdef")
        assert entry.is_sensitive

    def test_sensitive_detection_token(self):
        entry = ClipboardEntry(content="Bearer eyJhbGciOiJIUzI1NiJ9")
        assert entry.is_sensitive

    def test_sensitive_detection_secret(self):
        entry = ClipboardEntry(content="AWS_SECRET_ACCESS_KEY=abc123")
        assert entry.is_sensitive

    def test_normal_content(self):
        entry = ClipboardEntry(content="Hello, how are you?")
        assert not entry.is_sensitive

    def test_byte_size(self):
        entry = ClipboardEntry(content="hello")
        assert entry.byte_size == 5

    def test_to_dict(self):
        entry = ClipboardEntry(content="test", source_app="Safari", byte_size=4)
        d = entry.to_dict()
        assert d["source_app"] == "Safari"
        assert d["byte_size"] == 4


class TestClipboardSafetyFilter:
    def test_init_defaults(self):
        sf = ClipboardSafetyFilter()
        assert sf.scrub_sensitive is True
        assert sf.max_content_size == 1_000_000

    def test_check_read_always_allowed(self):
        sf = ClipboardSafetyFilter()
        entry = ClipboardEntry(content="anything")
        assert sf.check_read(entry) is True

    def test_check_write_normal_content(self):
        sf = ClipboardSafetyFilter()
        entry = ClipboardEntry(content="Hello World", byte_size=11)
        allowed, reason = sf.check_write(entry)
        assert allowed is True
        assert reason == ""

    def test_check_write_sensitive_scrubbed(self):
        sf = ClipboardSafetyFilter(scrub_sensitive=True)
        entry = ClipboardEntry(content="my password is secret123", byte_size=23)
        allowed, reason = sf.check_write(entry)
        assert allowed is False
        assert "Sensitive" in reason

    def test_check_write_oversized(self):
        sf = ClipboardSafetyFilter(max_content_size=10)
        entry = ClipboardEntry(content="a very long string of text", byte_size=27)
        allowed, reason = sf.check_write(entry)
        assert allowed is False
        assert "exceeds" in reason

    def test_detect_sensitive_patterns(self):
        sf = ClipboardSafetyFilter()
        patterns = sf.detect_sensitive("my API-KEY is sk-123 and password is secret")
        assert len(patterns) > 0
        assert "key" in patterns or "sk-" in patterns or "password" in patterns or "secret" in patterns

    def test_detect_no_sensitive(self):
        sf = ClipboardSafetyFilter()
        patterns = sf.detect_sensitive("The weather is nice today")
        assert len(patterns) == 0

    def test_access_log(self):
        sf = ClipboardSafetyFilter()
        entry = ClipboardEntry(content="test", byte_size=4)
        sf.check_write(entry)
        assert len(sf.access_log) == 1
        assert sf.access_log[0]["action"] == "write"


class TestClipboardController:
    def test_init_defaults(self):
        cc = ClipboardController()
        assert cc.dry_run is True

    def test_read_dry_run(self):
        cc = ClipboardController(dry_run=True)
        entry = cc.read()
        assert entry.content == "[dry_run clipboard content]"
        assert not entry.is_sensitive

    def test_write_dry_run(self):
        cc = ClipboardController(dry_run=True)
        assert cc.write("test content") is True

    def test_write_sensitive_dry_run(self):
        cc = ClipboardController(dry_run=True)
        result = cc.write("my password is secret")
        assert result is False

    def test_write_oversized_dry_run(self):
        sf = ClipboardSafetyFilter(max_content_size=5)
        cc = ClipboardController(safety_filter=sf, dry_run=True)
        result = cc.write("too long")
        assert result is False

    def test_clear_dry_run(self):
        cc = ClipboardController(dry_run=True)
        assert cc.clear() is True

    def test_dry_run_toggle(self):
        cc = ClipboardController(dry_run=True)
        cc.dry_run = False
        assert not cc.dry_run

    def test_get_access_log(self):
        cc = ClipboardController(dry_run=True)
        cc.write("hello")
        cc.write("world")
        log = cc.get_access_log()
        assert len(log) == 2


class TestVerificationResultFields:
    def test_defaults(self):
        result = VerificationResult(passed=True, method=VerificationMethod.ELEMENT_PRESENCE)
        assert result.before_image is None
        assert result.after_image is None
        assert result.diff_image is None
        assert result.diff_regions is None
        assert result.retry_count == 0
        assert result.duration_ms == 0.0
