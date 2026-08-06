from __future__ import annotations

import os
import tempfile

import pytest

from maref.recursive.recursive_evolution_loop import (
    RELTransactionManager,
    TransactionState,
)


class TestRELTransactionManager:
    @pytest.fixture
    def manager(self) -> RELTransactionManager:
        return RELTransactionManager(max_committed=5, max_rolled_back=3)

    def test_begin_creates_transaction(self, manager: RELTransactionManager) -> None:
        tx = manager.begin(["nonexistent_file.py"])
        assert tx.tx_id.startswith("tx_")
        assert tx.state == TransactionState.ACTIVE
        assert len(tx.snapshots) == 1

    def test_begin_snapshots_existing_file(self, manager: RELTransactionManager) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n")
            tmp_path = f.name

        try:
            tx = manager.begin([tmp_path])
            assert len(tx.snapshots) == 1
            assert tx.snapshots[0].path == tmp_path
            assert tx.snapshots[0].original_content == "x = 1\n"
            assert os.path.exists(tx.snapshots[0].backup_path)
        finally:
            os.unlink(tmp_path)

    def test_commit_removes_backups(self, manager: RELTransactionManager) -> None:
        tx = manager.begin(["test_commit_file.py"])
        assert os.path.exists(
            os.path.join(RELTransactionManager._SNAPSHOT_DIR, tx.tx_id)
        )
        result = manager.commit(tx)
        assert result is True
        assert tx.state == TransactionState.COMMITTED
        assert not os.path.exists(tx.snapshots[0].backup_path)

    def test_rollback_restores_content(self, manager: RELTransactionManager) -> None:
        import uuid
        tmp_path = os.path.join(
            tempfile.gettempdir(), f"rel_test_rollback_{uuid.uuid4().hex}.py"
        )
        try:
            with open(tmp_path, "w") as f:
                f.write("original_content\n")

            tx = manager.begin([tmp_path])

            with open(tmp_path, "w") as f:
                f.write("modified_content\n")

            with open(tmp_path) as f:
                assert f.read() == "modified_content\n"
            result = manager.rollback(tx)
            assert result is True
            assert tx.state == TransactionState.ROLLED_BACK
            with open(tmp_path) as f:
                assert f.read() == "original_content\n"
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_rollback_removes_generated_files(self, manager: RELTransactionManager) -> None:
        gen_path = os.path.join(tempfile.gettempdir(), "rel_test_generated.py")
        try:
            with open(gen_path, "w") as f:
                f.write("generated\n")

            tx = manager.begin([])
            tx.generated_files.append(gen_path)

            assert os.path.exists(gen_path)
            manager.rollback(tx)
            assert not os.path.exists(gen_path)
        finally:
            if os.path.exists(gen_path):
                os.unlink(gen_path)

    def test_get_by_id(self, manager: RELTransactionManager) -> None:
        tx = manager.begin(["file_a.py"])
        retrieved = manager.get(tx.tx_id)
        assert retrieved is not None
        assert retrieved.tx_id == tx.tx_id

    def test_get_nonexistent(self, manager: RELTransactionManager) -> None:
        assert manager.get("nonexistent") is None

    def test_get_by_round(self, manager: RELTransactionManager) -> None:
        tx1 = manager.begin(["file_a.py"])
        tx2 = manager.begin(["file_b.py"])
        round1_txs = manager.get_by_round(1)
        round2_txs = manager.get_by_round(2)
        assert tx1 in round1_txs
        assert tx2 in round2_txs

    def test_enforce_committed_limit(self) -> None:
        manager = RELTransactionManager(max_committed=2, max_rolled_back=1)
        txs = []
        for i in range(4):
            tx = manager.begin([f"file_{i}.py"])
            manager.commit(tx)
            txs.append(tx)

        active = [t for t in manager._txs.values() if t.state == TransactionState.COMMITTED]
        assert len(active) <= 2

    def test_enforce_rolled_back_limit(self) -> None:
        manager = RELTransactionManager(max_committed=2, max_rolled_back=1)
        txs = []
        for i in range(3):
            tx = manager.begin([f"rollback_file_{i}.py"])
            manager.rollback(tx)
            txs.append(tx)

        active = [t for t in manager._txs.values() if t.state == TransactionState.ROLLED_BACK]
        assert len(active) <= 1

    def test_rollback_nonexistent_file(self, manager: RELTransactionManager) -> None:
        tx = manager.begin(["/nonexistent/path/file.py"])
        result = manager.rollback(tx)
        assert result is True
