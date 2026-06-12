"""Tests for WarmPool — minimal tests for core logic.

Note: Full thread-based integration tests are excluded from CI
due to timing sensitivity. The core data structure and acquire/release
semantics are verified here.
"""

from maref.executor.warm_pool import WarmPool


class TestWarmPool:
    def test_start_spawns_min_workers(self):
        pool = WarmPool(min_size=2, max_size=10)
        pool.start()
        stats = pool.get_stats()
        assert stats["pool_size"] == 2
        pool.stop()

    def test_acquire_returns_warm_worker(self):
        pool = WarmPool(min_size=1, max_size=10)
        pool.start()
        worker = pool.acquire()
        assert worker is not None
        assert worker.is_busy
        pool.release(worker)
        pool.stop()

    def test_acquire_multiple_works(self):
        pool = WarmPool(min_size=2, max_size=10)
        pool.start()
        w1 = pool.acquire()
        w2 = pool.acquire()
        assert w1 is not None
        assert w2 is not None
        pool.release(w1)
        pool.release(w2)
        pool.stop()

    def test_release_returns_to_pool(self):
        pool = WarmPool(min_size=1, max_size=10)
        pool.start()
        worker = pool.acquire()
        pool.release(worker)
        w2 = pool.acquire()
        assert w2 is not None
        pool.release(w2)
        pool.stop()

    def test_get_stats(self):
        pool = WarmPool(min_size=2, max_size=10)
        pool.start()
        stats = pool.get_stats()
        assert stats["pool_size"] == 2
        assert stats["min_size"] == 2
        pool.stop()
