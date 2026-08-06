from __future__ import annotations

from maref.desktop.file_ops import (
    FileOpRequest,
    FileOpResult,
    FileOperation,
    FileOperator,
    FileSafetyGuard,
    SafetyVerdict,
)


class TestFileOpRequest:
    def test_to_dict(self) -> None:
        req = FileOpRequest(operation=FileOperation.READ, path="/tmp/test.txt")
        d = req.to_dict()
        assert d["operation"] == "read"
        assert d["path"] == "/tmp/test.txt"


class TestFileOpResult:
    def test_to_dict(self) -> None:
        result = FileOpResult(
            success=True,
            operation=FileOperation.READ,
            path="/tmp/test.txt",
            verdict=SafetyVerdict.ALLOW,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["verdict"] == "allow"


class TestFileSafetyGuard:
    def test_block_dangerous_operations(self) -> None:
        guard = FileSafetyGuard()
        for op in (FileOperation.CHMOD, FileOperation.EXEC):
            req = FileOpRequest(operation=op, path="/tmp/test.txt")
            assert guard.evaluate(req) == SafetyVerdict.BLOCK

    def test_block_restricted_path_write_sandboxes(self) -> None:
        guard = FileSafetyGuard()
        req = FileOpRequest(operation=FileOperation.WRITE, path="/etc/config.ini", content="data")
        assert guard.evaluate(req) == SafetyVerdict.SANDBOX

    def test_block_restricted_path_read(self) -> None:
        guard = FileSafetyGuard()
        req = FileOpRequest(operation=FileOperation.READ, path="/etc/passwd")
        assert guard.evaluate(req) == SafetyVerdict.BLOCK

    def test_allow_safe_path_read(self) -> None:
        guard = FileSafetyGuard()
        req = FileOpRequest(operation=FileOperation.READ, path="/tmp/test.txt")
        assert guard.evaluate(req) == SafetyVerdict.ALLOW

    def test_block_sensitive_extension_read(self) -> None:
        guard = FileSafetyGuard()
        req = FileOpRequest(operation=FileOperation.READ, path="/tmp/credentials.pem")
        assert guard.evaluate(req) == SafetyVerdict.BLOCK

    def test_block_sensitive_extension_copy(self) -> None:
        guard = FileSafetyGuard()
        req = FileOpRequest(operation=FileOperation.COPY, path="/tmp/id_rsa.pem", destination="/tmp/out")
        assert guard.evaluate(req) == SafetyVerdict.BLOCK

    def test_block_oversized_write(self) -> None:
        guard = FileSafetyGuard()
        content = "x" * (1024 * 1024 + 1)
        req = FileOpRequest(operation=FileOperation.WRITE, path="/tmp/test.txt", content=content)
        assert guard.evaluate(req) == SafetyVerdict.BLOCK

    def test_allow_home_delete(self) -> None:
        guard = FileSafetyGuard()
        import os
        req = FileOpRequest(operation=FileOperation.DELETE, path=os.path.expanduser("~/test.txt"))
        assert guard.evaluate(req) == SafetyVerdict.ALLOW

    def test_block_non_home_delete(self) -> None:
        guard = FileSafetyGuard()
        req = FileOpRequest(operation=FileOperation.DELETE, path="/var/log/test.log")
        assert guard.evaluate(req) == SafetyVerdict.BLOCK

    def test_block_destination_restricted(self) -> None:
        guard = FileSafetyGuard()
        req = FileOpRequest(
            operation=FileOperation.COPY,
            path="/tmp/test.txt",
            destination="/etc/passwd",
        )
        assert guard.evaluate(req) == SafetyVerdict.BLOCK

    def test_operation_log(self) -> None:
        guard = FileSafetyGuard()
        guard.evaluate(FileOpRequest(operation=FileOperation.READ, path="/etc/passwd"))
        guard.evaluate(FileOpRequest(operation=FileOperation.WRITE, path="/etc/x.conf", content="x"))
        assert len(guard.operation_log) >= 2

    def test_block_sensitive_file_name(self) -> None:
        guard = FileSafetyGuard()
        req = FileOpRequest(operation=FileOperation.READ, path="/tmp/.env")
        assert guard.evaluate(req) == SafetyVerdict.BLOCK


class TestFileOperator:
    def test_read_file_blocked(self) -> None:
        guard = FileSafetyGuard()
        op = FileOperator(safety_guard=guard, dry_run=True)
        result = op.read_file("/etc/passwd")
        assert not result.success

    def test_read_file_allowed_dry_run(self) -> None:
        op = FileOperator(dry_run=True)
        result = op.read_file("/tmp/test.txt")
        assert result.success
        assert "[DRY RUN]" in result.output

    def test_write_file_blocked_restricted(self) -> None:
        guard = FileSafetyGuard()
        op = FileOperator(safety_guard=guard, dry_run=True)
        result = op.write_file("/etc/config.ini", "data")
        assert result.success
        assert result.sandbox_path != ""

    def test_write_file_dry_run(self) -> None:
        op = FileOperator(dry_run=True)
        result = op.write_file("/tmp/test.txt", "hello")
        assert result.success

    def test_delete_file_dry_run(self) -> None:
        import os
        op = FileOperator(dry_run=True)
        result = op.delete_file(os.path.expanduser("~/test.txt"))
        assert result.success

    def test_move_file_dry_run(self) -> None:
        op = FileOperator(dry_run=True)
        result = op.move_file("/tmp/a.txt", "/tmp/b.txt")
        assert result.success

    def test_copy_file_dry_run(self) -> None:
        op = FileOperator(dry_run=True)
        result = op.copy_file("/tmp/a.txt", "/tmp/b.txt")
        assert result.success

    def test_list_directory_dry_run(self) -> None:
        op = FileOperator(dry_run=True)
        result = op.list_directory("/tmp")
        assert result.success

    def test_make_directory_dry_run(self) -> None:
        op = FileOperator(dry_run=True)
        result = op.make_directory("/tmp/newdir")
        assert result.success

    def test_dry_run_setter(self) -> None:
        op = FileOperator(dry_run=True)
        assert op.dry_run
        op.dry_run = False
        assert not op.dry_run

    def test_execute_operation_exception(self) -> None:
        import os
        op = FileOperator(dry_run=False)
        result = op.read_file("/nonexistent_path_12345/test.txt")
        assert not result.success

    def test_do_operation_read_write_roundtrip(self) -> None:
        import tempfile
        import os
        op = FileOperator(dry_run=False)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("orig")
            tmp = f.name
        try:
            result = op.write_file(tmp, "hello world")
            assert result.success
            result = op.read_file(tmp)
            assert result.success
            assert "hello world" in result.output
        finally:
            os.unlink(tmp)

    def test_do_operation_move(self) -> None:
        import tempfile
        import os
        op = FileOperator(dry_run=False)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("move me")
            src = f.name
        dst = src + ".moved"
        try:
            result = op.move_file(src, dst)
            assert result.success
            assert os.path.exists(dst)
            assert "Moved" in result.output
        finally:
            for p in (src, dst):
                if os.path.exists(p):
                    os.unlink(p)

    def test_do_operation_copy(self) -> None:
        import tempfile
        import os
        op = FileOperator(dry_run=False)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("copy me")
            src = f.name
        dst = src + ".copy"
        try:
            result = op.copy_file(src, dst)
            assert result.success
            assert os.path.exists(dst)
            assert "Copied" in result.output
        finally:
            for p in (src, dst):
                if os.path.exists(p):
                    os.unlink(p)

    def test_do_operation_list(self) -> None:
        import os
        op = FileOperator(dry_run=False)
        result = op.list_directory(os.path.dirname(os.path.abspath(__file__)))
        assert result.success
        assert "test_file_ops.py" in result.output

    def test_do_operation_mkdir(self) -> None:
        import tempfile
        import os
        op = FileOperator(dry_run=False)
        test_dir = os.path.join(tempfile.gettempdir(), "maref_fileops_mkdir_test")
        try:
            result = op.make_directory(test_dir)
            assert result.success
            assert "Created directory" in result.output
            assert os.path.isdir(test_dir)
        finally:
            if os.path.isdir(test_dir):
                os.rmdir(test_dir)

    def test_do_operation_delete_real(self) -> None:
        import os
        import tempfile
        op = FileOperator(dry_run=False)
        home = os.path.expanduser("~")
        tmp = os.path.join(home, ".maref_test_delete_temp.txt")
        try:
            result = op.write_file(tmp, "delete me")
            assert result.success
            result = op.delete_file(tmp)
            assert result.success
            assert "Deleted" in result.output
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
