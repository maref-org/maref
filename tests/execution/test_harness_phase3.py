"""Phase 3 测试：上下文管理 — LazyContextLoader + ContextCompressor + Harness 集成。"""

from __future__ import annotations

from maref.execution.context.compressor import ContextCompressor
from maref.execution.context.lazy_loader import LazyContextLoader
from maref.execution.harness.types import HarnessConfig
from maref.execution.harness.unified import UnifiedHarness


# ── LazyContextLoader ──────────────────────────────────────────────────────

class TestLazyContextLoader:
    def test_register_and_lazy_load(self) -> None:
        loader = LazyContextLoader()
        calls = 0

        def make_content() -> str:
            nonlocal calls
            calls += 1
            return "hello"

        loader.register("greeting", make_content)
        assert calls == 0  # loader not called yet
        assert loader.load("greeting") == "hello"
        assert calls == 1
        assert loader.loaded("greeting")

    def test_cache_returns_same_object(self) -> None:
        loader = LazyContextLoader()
        calls = 0

        def make() -> str:
            nonlocal calls
            calls += 1
            return "cached"

        loader.register("x", make)
        assert loader.load("x") == "cached"
        assert loader.load("x") == "cached"
        assert calls == 1  # second call from cache

    def test_prefetch_loads_before_access(self) -> None:
        loader = LazyContextLoader()
        loader.register("a", lambda: "A")
        loader.register("b", lambda: "B")
        assert not loader.loaded("a")
        loader.prefetch(["a", "b"])
        assert loader.loaded("a")
        assert loader.loaded("b")
        assert loader.load_count == 2

    def test_purge_removes_from_cache(self) -> None:
        loader = LazyContextLoader()
        loader.register("x", lambda: "data")
        loader.load("x")
        assert loader.loaded("x")
        loader.purge("x")
        assert not loader.loaded("x")
        # can load again after purge
        assert loader.load("x") == "data"

    def test_load_nonexistent_raises(self) -> None:
        loader = LazyContextLoader()
        try:
            loader.load("nope")
            assert False, "expected KeyError"
        except KeyError:
            pass

    def test_stats(self) -> None:
        loader = LazyContextLoader()
        loader.register("a", lambda: "1")
        loader.register("b", lambda: "2")
        loader.register("c", lambda: "3")
        loader.load("a")
        loader.load("b")
        stats = loader.stats()
        assert stats["total_registered"] == 3
        assert stats["loaded"] == 2
        assert stats["accesses"] == 2
        assert stats["loads"] == 2

    def test_total_count_and_keys(self) -> None:
        loader = LazyContextLoader()
        loader.register("a", lambda: "1")
        loader.register("b", lambda: "2")
        assert loader.total_count == 2
        assert sorted(loader.keys()) == ["a", "b"]


# ── ContextCompressor ──────────────────────────────────────────────────────

class TestContextCompressor:
    def test_estimate_tokens(self) -> None:
        c = ContextCompressor()
        assert c.estimate_tokens("hello") == 1  # 5 / 4 = 1.25 → 1
        assert c.estimate_tokens("a" * 100) == 25  # 100 / 4 = 25

    def test_compress_within_budget_unchanged(self) -> None:
        c = ContextCompressor()
        text = "short text"
        result = c.compress(text, budget=100)
        assert result == text

    def test_compress_truncates_when_over_budget(self) -> None:
        c = ContextCompressor()
        text = "A" * 1000
        result = c.compress(text, budget=50)  # ~200 chars budget
        assert c.estimate_tokens(result) <= 60  # allow some slack
        assert "[...truncated...]" in result

    def test_compress_protected_sections_kept(self) -> None:
        c = ContextCompressor()
        tool_def = "TOOL: read_file\nTOOL: write_file"
        history = "B" * 2000
        context = f"{tool_def}\n\n{history}"
        result = c.compress(context, budget=60, protected_sections=[tool_def])
        assert tool_def in result

    def test_compress_empty_string(self) -> None:
        c = ContextCompressor()
        assert c.compress("", budget=100) == ""

    def test_compress_exact_budget(self) -> None:
        c = ContextCompressor()
        text = "X" * 40  # ~10 tokens
        result = c.compress(text, budget=10)
        assert result == text  # exactly within budget

    def test_compress_very_small_budget_returns_placeholder(self) -> None:
        c = ContextCompressor()
        text = "A" * 500
        result = c.compress(text, budget=1)
        assert len(result) < len(text)
        assert "[...truncated...]" in result or result == ""

    def test_stats(self) -> None:
        c = ContextCompressor()
        stats = c.stats()
        assert "token_ratio" in stats


# ── UnifiedHarness 集成 ────────────────────────────────────────────────────

class TestContextIntegration:
    def test_context_property_empty_by_default(self) -> None:
        h = UnifiedHarness()
        assert h.context == {}

    def test_context_loader_in_constructor(self) -> None:
        loader = LazyContextLoader()
        h = UnifiedHarness(context_loader=loader)
        assert h._context_loader is loader

    def test_context_compressor_in_constructor(self) -> None:
        c = ContextCompressor()
        h = UnifiedHarness(context_compressor=c)
        assert h._context_compressor is c

    def test_context_loaded_during_run(self) -> None:
        loader = LazyContextLoader()
        loader.register("doc", lambda: "important document content")
        h = UnifiedHarness(context_loader=loader)
        h.configure(HarnessConfig())
        h.preflight()
        h.run()
        assert "doc" in h.context
        assert "important" in h.context["doc"]

    def test_context_compressed_when_over_budget(self) -> None:
        loader = LazyContextLoader()
        loader.register("big", lambda: "A" * 2000)
        comp = ContextCompressor()
        h = UnifiedHarness(context_loader=loader, context_compressor=comp)
        h.configure(HarnessConfig(token_budget=20))
        h.preflight()
        h.run()
        assert "[...truncated...]" in h.context["big"]

    def test_loader_error_does_not_crash(self) -> None:
        loader = LazyContextLoader()

        def failing() -> str:
            raise RuntimeError("oops")

        loader.register("fragile", failing)
        h = UnifiedHarness(context_loader=loader)
        h.configure(HarnessConfig())
        h.preflight()
        h.run()
        assert "error" in h.context["fragile"]
