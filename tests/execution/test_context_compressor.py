from __future__ import annotations

from maref.execution.context.compressor import ContextCompressor


class TestContextCompressor:
    def test_estimate_tokens(self) -> None:
        c = ContextCompressor()
        assert c.estimate_tokens("hello") == 1
        assert c.estimate_tokens("") == 1
        assert c.estimate_tokens("a" * 40) == 10

    def test_compress_short_text_within_budget(self) -> None:
        c = ContextCompressor()
        text = "Hello, world!"
        result = c.compress(text, budget=100)
        assert result == text

    def test_compress_long_text(self) -> None:
        c = ContextCompressor()
        text = "word " * 1000
        result = c.compress(text, budget=100)
        assert isinstance(result, str)
        assert len(result) < len(text)
        assert "[...truncated...]" in result

    def test_compress_empty(self) -> None:
        c = ContextCompressor()
        assert c.compress("", budget=100) == ""

    def test_compress_with_protected_sections(self) -> None:
        c = ContextCompressor()
        text = "prefix " * 100 + "PROTECTED" + " suffix " * 100
        result = c.compress(text, budget=50, protected_sections=["PROTECTED"])
        assert "PROTECTED" in result
        assert "[...truncated...]" in result

    def test_compress_protected_only_fits(self) -> None:
        c = ContextCompressor()
        text = "a" * 1000
        result = c.compress(text, budget=5, protected_sections=["SHORT"])
        assert "SHORT" in result

    def test_stats(self) -> None:
        c = ContextCompressor()
        s = c.stats()
        assert isinstance(s, dict)
        assert s["token_ratio"] == 4.0
