from __future__ import annotations

import pytest

from maref.desktop.verification import (
    DiffRegion,
    DiffSeverity,
    OperationVerifier,
    ScreenshotVerifier,
    VerificationMethod,
    VerificationResult,
)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class TestScreenshotVerifier:
    def test_init_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            ScreenshotVerifier(diff_threshold=0.0)
        with pytest.raises(ValueError):
            ScreenshotVerifier(diff_threshold=1.5)

    @pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
    def test_compare_identical_images(self) -> None:
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        verifier = ScreenshotVerifier(diff_threshold=0.05)
        result = verifier.compare(img, img)
        assert result.passed
        assert result.diff_percentage == 0.0
        assert result.method == VerificationMethod.SCREENSHOT_DIFF

    @pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
    def test_compare_different_images(self) -> None:
        before = Image.new("RGB", (100, 100), color=(128, 128, 128))
        after = Image.new("RGB", (100, 100), color=(255, 255, 255))
        verifier = ScreenshotVerifier(diff_threshold=0.001)
        result = verifier.compare(before, after)
        assert not result.passed
        assert result.diff_percentage > 0.01

    @pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
    def test_compare_size_mismatch(self) -> None:
        img1 = Image.new("RGB", (100, 100))
        img2 = Image.new("RGB", (200, 200))
        verifier = ScreenshotVerifier()
        result = verifier.compare(img1, img2)
        assert not result.passed
        assert "size mismatch" in result.details.lower()

    @pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
    def test_compare_with_expected_regions(self) -> None:
        before = Image.new("RGB", (100, 100), color=(0, 0, 0))
        after = Image.new("RGB", (100, 100), color=(0, 0, 0))
        for x in range(10, 20):
            for y in range(10, 20):
                after.putpixel((x, y), (255, 255, 255))
        verifier = ScreenshotVerifier(diff_threshold=0.05)
        result = verifier.compare(before, after)
        assert result.passed
        assert result.diff_percentage > 0

    def test_benchmark_no_pil(self) -> None:
        result = ScreenshotVerifier.benchmark((100, 100))
        if not HAS_PIL:
            assert "error" in result
        else:
            assert "avg_comparison_ms" in result

    def test_verify_with_retry_returns_result(self) -> None:
        verifier = ScreenshotVerifier()
        img = Image.new("RGB", (10, 10)) if HAS_PIL else None
        result = verifier.verify_with_retry(
            capture_before=lambda: img,
            execute_action=lambda: True,
            capture_after=lambda: img,
            max_retries=1,
        )
        assert isinstance(result, VerificationResult)


class TestDiffRegion:
    def test_to_dict(self) -> None:
        region = DiffRegion(
            x=10, y=20, width=100, height=50,
            severity=DiffSeverity.MAJOR, diff_percentage=0.75,
        )
        d = region.to_dict()
        assert d["x"] == 10
        assert d["severity"] == "major"
        assert d["diff_percentage"] == 0.75


class TestVerificationResult:
    def test_to_dict(self) -> None:
        result = VerificationResult(
            passed=True,
            method=VerificationMethod.TEXT_MATCH,
            details="Found expected text",
            diff_percentage=0.0,
            retry_count=1,
            duration_ms=100.0,
        )
        d = result.to_dict()
        assert d["passed"] is True
        assert d["method"] == "text_match"
        assert d["retry_count"] == 1


class TestOperationVerifier:
    def test_no_screenshot_verifier_default(self) -> None:
        verifier = OperationVerifier()
        if HAS_PIL:
            assert verifier._screenshot_verifier is not None

    def test_regions_overlap(self) -> None:
        verifier = OperationVerifier()
        a = DiffRegion(x=0, y=0, width=100, height=100)
        b = DiffRegion(x=50, y=50, width=100, height=100)
        assert verifier._regions_overlap(a, b)
        assert verifier._regions_overlap(b, a)

    def test_regions_no_overlap(self) -> None:
        verifier = OperationVerifier()
        a = DiffRegion(x=0, y=0, width=10, height=10)
        b = DiffRegion(x=100, y=100, width=10, height=10)
        assert not verifier._regions_overlap(a, b)
