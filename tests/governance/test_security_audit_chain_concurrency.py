from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

import pytest

from maref.governance.security_audit_chain import SecurityAuditChain


def _append_many(path: str, key: bytes, count: int) -> None:
    chain = SecurityAuditChain(Path(path), hmac_key=key)
    for index in range(count):
        chain.append("concurrent", f"pid-{os.getpid()}", f"action-{index}")


def test_multiple_instances_do_not_fork(tmp_path: Path) -> None:
    path = tmp_path / "security_audit.chain"
    chains = [
        SecurityAuditChain(path, hmac_key="test-key"),
        SecurityAuditChain(path, hmac_key="test-key"),
        SecurityAuditChain(path, hmac_key="test-key"),
    ]

    for index, chain in enumerate(chains):
        chain.append("sequential", "actor", f"action-{index}")

    result = SecurityAuditChain(path, hmac_key="test-key").verify_integrity()
    assert result["status"] == "verified"
    assert result["total"] == 3
    assert result["tampered"] == 0


def test_multiprocess_appends_keep_chain_linear(tmp_path: Path) -> None:
    try:
        context = multiprocessing.get_context("fork")
    except ValueError:
        pytest.skip("fork start method unavailable")

    path = tmp_path / "security_audit.chain"
    process_count = 4
    per_process = 10
    processes = [
        context.Process(
            target=_append_many,
            args=(str(path), b"test-key", per_process),
        )
        for _ in range(process_count)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    result = SecurityAuditChain(path, hmac_key="test-key").verify_integrity()
    assert result["status"] == "verified"
    assert result["total"] == process_count * per_process
    assert result["tampered"] == 0
