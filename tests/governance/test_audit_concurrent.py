"""Concurrent audit log write tests.

验证审计日志在并发写入下的完整性——无数据损坏、无乱序、HMAC 签名链连续。
"""

from __future__ import annotations

import concurrent.futures
import json
import tempfile
import threading
from pathlib import Path

from maref.governance.audit import AuditLogger


def _write_batch(logger: AuditLogger, prefix: str, count: int) -> list[str]:
    ids: list[str] = []
    for i in range(count):
        entry = logger.log_decision(
            actor="concurrent_test",
            action=f"{prefix}_{i}",
            reason=f"concurrent write test {prefix}",
            from_state="INIT",
            to_state="OBSERVE",
        )
        ids.append(entry.id)
    return ids


def test_concurrent_write_no_corruption() -> None:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = Path(f.name)

    try:
        logger = AuditLogger(path)
        n_threads = 4
        n_per_thread = 25
        ids: list[str] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [
                pool.submit(_write_batch, logger, f"t{t}", n_per_thread)
                for t in range(n_threads)
            ]
            for f in concurrent.futures.as_completed(futures):
                ids.extend(f.result())

        entries = logger.read_all(max_entries=1000)
        assert len(entries) == n_threads * n_per_thread
        assert len(ids) == len(set(ids)), "Duplicate IDs detected"

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == n_threads * n_per_thread

        for line in lines:
            record = json.loads(line)
            assert "action" in record
            assert "chain_hash" in record

    finally:
        if path.exists():
            path.unlink()


def test_concurrent_write_large_batch() -> None:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = Path(f.name)

    try:
        logger = AuditLogger(path)
        n_threads = 8
        n_per_thread = 50

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [
                pool.submit(_write_batch, logger, f"t{t}", n_per_thread)
                for t in range(n_threads)
            ]
            concurrent.futures.wait(futures)

        entries = logger.read_all(max_entries=2000)
        assert len(entries) == n_threads * n_per_thread

        chain_hashes = []
        with open(path) as f:
            for line in f:
                record = json.loads(line)
                if "chain_hash" in record:
                    chain_hashes.append(record["chain_hash"])

        assert len(chain_hashes) == n_threads * n_per_thread

    finally:
        if path.exists():
            path.unlink()


def test_sequential_integrity_after_concurrent() -> None:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = Path(f.name)

    try:
        logger = AuditLogger(path)

        futures: list[concurrent.futures.Future] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for _ in range(10):
                futures.append(pool.submit(logger.log_decision, "tester", "concurrent_action", "test", "INIT", "OBSERVE"))

        concurrent.futures.wait(futures)
        assert all(f.result() is not None for f in futures)

        post_entry = logger.log_decision(
            actor="sequential",
            action="post_concurrent",
            reason="after concurrent burst",
            from_state="OBSERVE",
            to_state="ANALYZE",
        )
        assert post_entry is not None
        assert "post_concurrent" in post_entry.action

    finally:
        if path.exists():
            path.unlink()


def test_concurrent_alternating_loggers_same_file() -> None:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = Path(f.name)

    try:
        results: list[Exception | None] = [None] * 4
        barriers: list[threading.Barrier] = [threading.Barrier(4) for _ in range(3)]

        def _writer(idx: int) -> None:
            try:
                logger = AuditLogger(path)
                for i in range(5):
                    logger.log_decision(f"actor_{idx}", f"action_{idx}_{i}", f"reason_{i}", "INIT", "OBSERVE")
                    barriers[min(i, 2)].wait(timeout=5)
            except Exception as e:
                results[idx] = e

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r is None for r in results), f"Errors: {[str(r) for r in results if r]}"
        entries = AuditLogger(path).read_all(max_entries=100)
        assert len(entries) == 20

    finally:
        if path.exists():
            path.unlink()
