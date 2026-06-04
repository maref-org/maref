"""Warm pool — pre-warmed worker instances for low-latency cold start.

Workers are pre-spawned and held in a hot pool. When a task arrives,
an already-warm worker picks it up immediately instead of spawning
a new thread (cold start). Workers idle for `keep_alive_seconds`
before being stopped.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class WarmWorker:
    """A pre-warmed worker kept alive in the pool."""

    def __init__(self, worker_id: str, keep_alive: float = 30.0) -> None:
        self.id = worker_id
        self._keep_alive = keep_alive
        self._last_used = time.time()
        self._busy = False
        self._stop = threading.Event()

    @property
    def is_expired(self) -> bool:
        return not self._busy and (time.time() - self._last_used) > self._keep_alive

    @property
    def is_busy(self) -> bool:
        return self._busy

    def acquire(self) -> bool:
        if self._busy:
            return False
        self._busy = True
        return True

    def release(self) -> None:
        self._busy = False
        self._last_used = time.time()


class WarmPool:
    """Pool of pre-warmed workers for low-latency task execution.

    Usage:
        pool = WarmPool(min_size=2, max_size=10)
        pool.start()

        # Acquire a warm worker
        worker = pool.acquire()
        if worker:
            # Execute task...
            pool.release(worker)
        else:
            # All busy, fall back to cold start
            pass
    """

    def __init__(
        self,
        min_size: int = 2,
        max_size: int = 10,
        keep_alive: float = 30.0,
    ) -> None:
        self._min = min_size
        self._max = max_size
        self._keep_alive = keep_alive
        self._workers: list[WarmWorker] = []
        self._lock = threading.Lock()
        self._next_id = 0
        self._stop_event = threading.Event()
        self._maintainer: threading.Thread | None = None
        self._hits = 0   # Successful warm acquisitions
        self._misses = 0  # Cold start fallbacks

    def start(self) -> None:
        self._stop_event.clear()
        with self._lock:
            for _ in range(self._min):
                self._spawn_worker()
        self._maintainer = threading.Thread(
            target=self._maintain_loop,
            name="warm-pool-maintainer",
            daemon=True,
        )
        self._maintainer.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop_event.set()
        if self._maintainer:
            self._maintainer.join(timeout=timeout)

    def acquire(self) -> WarmWorker | None:
        """Acquire a warm worker. Returns None if all busy."""
        with self._lock:
            for w in self._workers:
                if w.acquire():
                    self._hits += 1
                    return w
            self._misses += 1
            # Optionally spawn on-demand if under max
            if len(self._workers) < self._max:
                worker = self._spawn_worker()
                worker.acquire()
                return worker
            return None

    def release(self, worker: WarmWorker) -> None:
        worker.release()

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 1.0

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pool_size": len(self._workers),
                "busy": sum(1 for w in self._workers if w.is_busy),
                "idle": sum(1 for w in self._workers if not w.is_busy),
                "min_size": self._min,
                "max_size": self._max,
                "keep_alive": self._keep_alive,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self.hit_rate, 3),
            }

    def _spawn_worker(self) -> WarmWorker:
        wid = f"warm-{self._next_id}"
        self._next_id += 1
        worker = WarmWorker(wid, keep_alive=self._keep_alive)
        self._workers.append(worker)
        return worker

    def _maintain_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(0.5)
            with self._lock:
                # Remove expired workers (but keep at least min_size)
                expired = [w for w in self._workers if w.is_expired and not w.is_busy]
                to_remove = len(expired)
                # Ensure we don't go below min
                if len(self._workers) - to_remove < self._min:
                    to_remove = max(0, len(self._workers) - self._min)
                for w in expired[:to_remove]:
                    self._workers.remove(w)

                # Top up to min_size
                while len(self._workers) < self._min:
                    self._spawn_worker()
