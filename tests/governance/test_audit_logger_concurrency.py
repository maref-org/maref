from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

import pytest

from maref.governance.audit import AuditLogger


def _write_many(path: str, key: bytes, count: int, max_size: int) -> None:
    logger = AuditLogger(Path(path), hmac_key=key, max_file_size_mb=0)
    logger._max_file_size = max_size
    for index in range(count):
        logger.log("concurrent", f"pid-{os.getpid()}", f"action-{index}")


def _read_records(path: Path) -> list[dict]:
    records: list[dict] = []
    candidates = [path, *sorted(path.parent.glob(f"{path.stem}_*{path.suffix}"))]
    for candidate in candidates:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def test_rotation_does_not_overwrite_same_second_archive(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path, hmac_key="test-key", max_file_size_mb=0)
    logger._max_file_size = 1

    for index in range(3):
        logger.log("rotation", "actor", f"action-{index}")

    rotated = sorted(path.parent.glob(f"{path.stem}_*{path.suffix}"))
    assert len(rotated) == 2
    assert len(_read_records(path)) == 3


def test_multiprocess_writers_do_not_lose_records(tmp_path: Path) -> None:
    try:
        context = multiprocessing.get_context("fork")
    except ValueError:
        pytest.skip("fork start method unavailable")

    path = tmp_path / "audit.jsonl"
    process_count = 4
    per_process = 10
    processes = [
        context.Process(
            target=_write_many,
            args=(str(path), b"test-key", per_process, 400),
        )
        for _ in range(process_count)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    records = _read_records(path)
    assert len(records) == process_count * per_process
    assert len({record["id"] for record in records}) == process_count * per_process
    assert len(sorted(path.parent.glob(f"{path.stem}_*{path.suffix}"))) >= 2


def test_partial_tail_is_repaired_before_append(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path, hmac_key="test-key")
    first = logger.log("first", "actor", "action")

    with open(path, "ab") as handle:
        handle.write(b'{"broken":')

    second = logger.log("second", "actor", "action")
    records = _read_records(path)

    assert len(records) == 2
    assert records[0]["id"] == first.id
    assert records[1]["id"] == second.id
    assert records[1]["previous_hash"] == first.chain_hash


def test_complete_tail_without_newline_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path, hmac_key="test-key")
    first = logger.log("first", "actor", "action")

    path.write_text(path.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")

    second = logger.log("second", "actor", "action")
    records = _read_records(path)

    assert len(records) == 2
    assert records[0]["id"] == first.id
    assert records[1]["id"] == second.id
    assert records[1]["previous_hash"] == first.chain_hash
