from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from maref.integration.mcp_transport import InProcessTransport
from maref.tools.file_server import (
    PathSandbox,
    PathSandboxError,
    create_file_server,
)


@pytest.fixture
def temp_dir() -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sandbox(temp_dir: str) -> PathSandbox:
    return PathSandbox(allowed_bases=[temp_dir])


@pytest.fixture
def file_server(temp_dir: str) -> InProcessTransport:
    server = create_file_server(
        name="test-file-server",
        version="0.1.0",
        allowed_bases=[temp_dir],
        max_read_size=1024,
    )
    transport = server.get_inprocess_transport()
    transport.connect()
    return transport


class TestPathSandbox:
    def test_validate_allowed_path(self, sandbox: PathSandbox, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "test.txt")
        result = sandbox.validate(test_file)
        assert result == os.path.realpath(test_file)

    def test_validate_path_traversal_blocked(self, sandbox: PathSandbox) -> None:
        with pytest.raises(PathSandboxError):
            sandbox.validate("/etc/passwd")

    def test_validate_relative_path_traversal(self, sandbox: PathSandbox) -> None:
        with pytest.raises(PathSandboxError):
            sandbox.validate("../escape.txt")

    def test_resolve_absolute(self, sandbox: PathSandbox, temp_dir: str) -> None:
        result = sandbox.resolve(os.path.join(temp_dir, "sub", "file.txt"))
        assert os.path.isabs(result)

    def test_allowed_bases_property(self, sandbox: PathSandbox, temp_dir: str) -> None:
        bases = sandbox.allowed_bases
        assert len(bases) == 1
        assert bases[0] == os.path.realpath(temp_dir)

    def test_default_uses_cwd(self) -> None:
        sandbox = PathSandbox()
        assert os.getcwd() in sandbox.allowed_bases


class TestReadFile:
    def test_read_existing_file(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "hello.txt")
        Path(test_file).write_text("Hello, MAREF!", encoding="utf-8")

        resp = file_server.send_tool_call("read_file", {"path": test_file})
        assert not resp.is_error
        assert resp.result["content"] == "Hello, MAREF!"
        assert resp.result["size"] == 13
        assert resp.result["encoding"] == "utf-8"

    def test_read_non_existent_file(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call("read_file", {"path": os.path.join(temp_dir, "nope.txt")})
        assert resp.is_error

    def test_read_with_encoding(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "encoded.txt")
        text = "你好，世界"
        Path(test_file).write_text(text, encoding="utf-8")

        resp = file_server.send_tool_call("read_file", {"path": test_file, "encoding": "utf-8"})
        assert not resp.is_error
        assert resp.result["content"] == text

    def test_read_beyond_size_limit(self, temp_dir: str) -> None:
        server = create_file_server(
            name="limited-server",
            allowed_bases=[temp_dir],
            max_read_size=10,
        )
        transport = server.get_inprocess_transport()
        transport.connect()

        test_file = os.path.join(temp_dir, "large.txt")
        Path(test_file).write_text("x" * 100, encoding="utf-8")

        resp = transport.send_tool_call("read_file", {"path": test_file})
        assert resp.is_error


class TestWriteFile:
    def test_write_new_file(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "new.txt")
        resp = file_server.send_tool_call(
            "write_file", {"path": test_file, "content": "test content"}
        )
        assert not resp.is_error
        assert resp.result["success"] is True
        assert resp.result["size"] == 12
        assert os.path.exists(resp.result["path"])

    def test_write_with_encoding(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "utf8.txt")
        resp = file_server.send_tool_call(
            "write_file", {"path": test_file, "content": "你好", "encoding": "utf-8"}
        )
        assert not resp.is_error
        content = Path(test_file).read_text(encoding="utf-8")
        assert content == "你好"

    def test_write_outside_sandbox(self, file_server: InProcessTransport) -> None:
        resp = file_server.send_tool_call(
            "write_file", {"path": "/etc/evil.txt", "content": "malicious"}
        )
        assert resp.is_error


class TestListDirectory:
    def test_list_empty_dir(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call("list_directory", {"path": temp_dir})
        assert not resp.is_error
        assert resp.result["items"] == []

    def test_list_with_files(self, file_server: InProcessTransport, temp_dir: str) -> None:
        Path(os.path.join(temp_dir, "a.txt")).write_text("aaa")
        Path(os.path.join(temp_dir, "b.txt")).write_text("bbb")
        os.mkdir(os.path.join(temp_dir, "subdir"))

        resp = file_server.send_tool_call("list_directory", {"path": temp_dir})
        assert not resp.is_error
        items = resp.result["items"]
        assert len(items) == 3

        dirs = [i for i in items if i["type"] == "dir"]
        files = [i for i in items if i["type"] == "file"]
        assert len(dirs) == 1
        assert dirs[0]["name"] == "subdir"
        assert len(files) == 2

    def test_list_with_pattern(self, file_server: InProcessTransport, temp_dir: str) -> None:
        Path(os.path.join(temp_dir, "data.json")).write_text("{}")
        Path(os.path.join(temp_dir, "data.xml")).write_text("<r/>")
        Path(os.path.join(temp_dir, "readme.md")).write_text("# Hi")

        resp = file_server.send_tool_call(
            "list_directory", {"path": temp_dir, "pattern": "*.json"}
        )
        assert not resp.is_error
        names = [i["name"] for i in resp.result["items"]]
        assert names == ["data.json"]

    def test_list_non_existent_dir(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call(
            "list_directory", {"path": os.path.join(temp_dir, "nonexistent")}
        )
        assert resp.is_error


class TestDeleteFile:
    def test_delete_file(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "todelete.txt")
        Path(test_file).write_text("bye")
        assert os.path.exists(test_file)

        resp = file_server.send_tool_call("delete_file", {"path": test_file})
        assert not resp.is_error
        assert resp.result["success"] is True
        assert not os.path.exists(test_file)

    def test_delete_non_existent(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call(
            "delete_file", {"path": os.path.join(temp_dir, "ghost.txt")}
        )
        assert resp.is_error


class TestCopyFile:
    def test_copy_file(self, file_server: InProcessTransport, temp_dir: str) -> None:
        src = os.path.join(temp_dir, "source.txt")
        dst = os.path.join(temp_dir, "dest.txt")
        Path(src).write_text("copy me")

        resp = file_server.send_tool_call("copy_file", {"source": src, "destination": dst})
        assert not resp.is_error
        assert resp.result["success"] is True
        assert os.path.exists(dst)
        assert Path(dst).read_text() == "copy me"

    def test_copy_to_subdir(self, file_server: InProcessTransport, temp_dir: str) -> None:
        src = os.path.join(temp_dir, "source.txt")
        dst = os.path.join(temp_dir, "sub", "dest.txt")
        Path(src).write_text("copy")

        resp = file_server.send_tool_call("copy_file", {"source": src, "destination": dst})
        assert not resp.is_error
        assert os.path.exists(dst)

    def test_copy_outside_sandbox(self, file_server: InProcessTransport, temp_dir: str) -> None:
        src = os.path.join(temp_dir, "source.txt")
        Path(src).write_text("data")

        resp = file_server.send_tool_call(
            "copy_file", {"source": src, "destination": "/tmp/outside.txt"}
        )
        assert resp.is_error


class TestMoveFile:
    def test_move_file(self, file_server: InProcessTransport, temp_dir: str) -> None:
        src = os.path.join(temp_dir, "move_src.txt")
        dst = os.path.join(temp_dir, "move_dst.txt")
        Path(src).write_text("move me")

        resp = file_server.send_tool_call("move_file", {"source": src, "destination": dst})
        assert not resp.is_error
        assert resp.result["success"] is True
        assert os.path.exists(dst)
        assert not os.path.exists(src)

    def test_move_to_subdir(self, file_server: InProcessTransport, temp_dir: str) -> None:
        src = os.path.join(temp_dir, "source.txt")
        dst = os.path.join(temp_dir, "sub", "dest.txt")
        Path(src).write_text("move")

        resp = file_server.send_tool_call("move_file", {"source": src, "destination": dst})
        assert not resp.is_error
        assert os.path.exists(dst)
        assert not os.path.exists(src)


class TestGetFileInfo:
    def test_get_file_info(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "info.txt")
        Path(test_file).write_text("metadata")

        resp = file_server.send_tool_call("get_file_info", {"path": test_file})
        assert not resp.is_error
        info = resp.result
        assert info["path"] == os.path.realpath(test_file)
        assert info["size"] == 8
        assert "modified" in info
        assert info["is_dir"] is False

    def test_get_dir_info(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call("get_file_info", {"path": temp_dir})
        assert not resp.is_error
        assert resp.result["is_dir"] is True
        assert resp.result["size"] == 0

    def test_get_info_non_existent(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call(
            "get_file_info", {"path": os.path.join(temp_dir, "ghost.txt")}
        )
        assert resp.is_error


class TestSecurity:
    def test_path_traversal_dotdot(self, sandbox: PathSandbox, temp_dir: str) -> None:
        with pytest.raises(PathSandboxError):
            sandbox.validate(os.path.join(temp_dir, "..", "etc", "passwd"))

    def test_path_traversal_absolute(self, sandbox: PathSandbox) -> None:
        with pytest.raises(PathSandboxError):
            sandbox.validate("/var/log/system.log")

    def test_path_traversal_symlink_attack(self, sandbox: PathSandbox, temp_dir: str) -> None:
        link_path = os.path.join(temp_dir, "evil_link")
        target = "/etc/passwd"
        try:
            os.symlink(target, link_path)
            with pytest.raises(PathSandboxError):
                sandbox.validate(link_path)
        except OSError:
            pass

    def test_sandbox_with_symlink_to_allowed(self, sandbox: PathSandbox, temp_dir: str) -> None:
        real_dir = os.path.join(temp_dir, "real_sub")
        os.makedirs(real_dir)
        link_path = os.path.join(temp_dir, "link_to_sub")
        try:
            os.symlink(real_dir, link_path)
            result = sandbox.validate(os.path.join(link_path, "file.txt"))
            assert result.startswith(os.path.realpath(real_dir))
        except OSError:
            pass

    def test_file_size_limit(self, temp_dir: str) -> None:
        server = create_file_server(
            allowed_bases=[temp_dir],
            max_read_size=5,
        )
        transport = server.get_inprocess_transport()
        transport.connect()

        test_file = os.path.join(temp_dir, "big.txt")
        Path(test_file).write_text("hello world", encoding="utf-8")

        resp = transport.send_tool_call("read_file", {"path": test_file})
        assert resp.is_error

    def test_list_dir_outside_sandbox(self, file_server: InProcessTransport) -> None:
        resp = file_server.send_tool_call("list_directory", {"path": "/etc"})
        assert resp.is_error

    def test_delete_outside_sandbox(self, file_server: InProcessTransport) -> None:
        resp = file_server.send_tool_call("delete_file", {"path": "/etc/hosts"})
        assert resp.is_error

    def test_copy_source_outside_sandbox(self, file_server: InProcessTransport, temp_dir: str) -> None:
        dst = os.path.join(temp_dir, "dest.txt")
        resp = file_server.send_tool_call(
            "copy_file", {"source": "/etc/hosts", "destination": dst}
        )
        assert resp.is_error

    def test_move_dest_outside_sandbox(self, file_server: InProcessTransport, temp_dir: str) -> None:
        src = os.path.join(temp_dir, "src.txt")
        Path(src).write_text("data")
        resp = file_server.send_tool_call(
            "move_file", {"source": src, "destination": "/tmp/outside.txt"}
        )
        assert resp.is_error

    def test_get_info_outside_sandbox(self, file_server: InProcessTransport) -> None:
        resp = file_server.send_tool_call("get_file_info", {"path": "/etc/hosts"})
        assert resp.is_error

    def test_empty_sandbox_blocks_all(self) -> None:
        server = create_file_server(allowed_bases=["/nonexistent_sandbox_xyz"])
        transport = server.get_inprocess_transport()
        transport.connect()

        resp = transport.send_tool_call("read_file", {"path": "/etc/hosts"})
        assert resp.is_error


class TestErrorCases:
    def test_read_non_existent_file(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call(
            "read_file", {"path": os.path.join(temp_dir, "no_such_file.txt")}
        )
        assert resp.is_error

    def test_list_non_existent_path(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call(
            "list_directory", {"path": os.path.join(temp_dir, "no_such_dir")}
        )
        assert resp.is_error

    def test_get_info_non_existent_path(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call(
            "get_file_info", {"path": os.path.join(temp_dir, "no_such_file.txt")}
        )
        assert resp.is_error

    def test_delete_non_existent_path(self, file_server: InProcessTransport, temp_dir: str) -> None:
        resp = file_server.send_tool_call(
            "delete_file", {"path": os.path.join(temp_dir, "no_such_file.txt")}
        )
        assert resp.is_error

    def test_copy_non_existent_source(self, file_server: InProcessTransport, temp_dir: str) -> None:
        src = os.path.join(temp_dir, "no_such_source.txt")
        dst = os.path.join(temp_dir, "dest.txt")
        resp = file_server.send_tool_call("copy_file", {"source": src, "destination": dst})
        assert resp.is_error

    def test_move_non_existent_source(self, file_server: InProcessTransport, temp_dir: str) -> None:
        src = os.path.join(temp_dir, "no_such_source.txt")
        dst = os.path.join(temp_dir, "dest.txt")
        resp = file_server.send_tool_call("move_file", {"source": src, "destination": dst})
        assert resp.is_error


class TestEndToEnd:
    def test_write_then_read(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "e2e.txt")

        write_resp = file_server.send_tool_call(
            "write_file", {"path": test_file, "content": "Hello World"}
        )
        assert not write_resp.is_error

        read_resp = file_server.send_tool_call("read_file", {"path": test_file})
        assert not read_resp.is_error
        assert read_resp.result["content"] == "Hello World"

    def test_write_copy_move_cycle(self, file_server: InProcessTransport, temp_dir: str) -> None:
        original = os.path.join(temp_dir, "original.txt")
        copied = os.path.join(temp_dir, "copied.txt")
        moved = os.path.join(temp_dir, "moved.txt")

        file_server.send_tool_call("write_file", {"path": original, "content": "cycle test"})

        copy_resp = file_server.send_tool_call(
            "copy_file", {"source": original, "destination": copied}
        )
        assert not copy_resp.is_error

        assert Path(copied).read_text() == "cycle test"

        move_resp = file_server.send_tool_call(
            "move_file", {"source": copied, "destination": moved}
        )
        assert not move_resp.is_error
        assert not os.path.exists(copied)
        assert os.path.exists(moved)

    def test_delete_and_verify(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "delete_me.txt")
        Path(test_file).write_text("temp")

        del_resp = file_server.send_tool_call("delete_file", {"path": test_file})
        assert not del_resp.is_error

        read_resp = file_server.send_tool_call("read_file", {"path": test_file})
        assert read_resp.is_error

    def test_list_dir_with_mixed_content(self, file_server: InProcessTransport, temp_dir: str) -> None:
        Path(os.path.join(temp_dir, "alpha.txt")).write_text("a")
        Path(os.path.join(temp_dir, "beta.txt")).write_text("b")
        os.mkdir(os.path.join(temp_dir, "gamma"))

        resp = file_server.send_tool_call("list_directory", {"path": temp_dir})
        assert not resp.is_error
        items = resp.result["items"]
        names = [i["name"] for i in items]
        assert names == ["gamma", "alpha.txt", "beta.txt"]

    def test_get_info_after_write(self, file_server: InProcessTransport, temp_dir: str) -> None:
        test_file = os.path.join(temp_dir, "info_test.txt")
        file_server.send_tool_call("write_file", {"path": test_file, "content": "info please"})

        resp = file_server.send_tool_call("get_file_info", {"path": test_file})
        assert not resp.is_error
        assert resp.result["size"] == 11
        assert resp.result["is_dir"] is False

    def test_list_directory_default_path(self, file_server: InProcessTransport, temp_dir: str) -> None:
        Path(os.path.join(temp_dir, "default.txt")).write_text("x")

        resp = file_server.send_tool_call("list_directory", {"path": temp_dir})
        assert not resp.is_error
        assert len(resp.result["items"]) == 1


class TestFactoryDefaults:
    def test_default_server_name(self) -> None:
        server = create_file_server()
        assert server.name == "maref-file-server"
        assert server.version == "0.25.0"

    def test_custom_server_name(self) -> None:
        server = create_file_server(name="custom", version="1.0.0")
        assert server.name == "custom"
        assert server.version == "1.0.0"
