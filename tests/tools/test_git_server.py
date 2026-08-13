from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from maref.integration.mcp_envelope import make_envelope
from maref.integration.mcp_transport import JSONRPCRequest
from maref.tools.git_server import GitServer, RepoWhitelist, create_git_server


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )


def _make_commit(path: Path, filename: str, content: str, message: str) -> None:
    (path / filename).write_text(content)
    subprocess.run(["git", "add", filename], cwd=path, capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message], cwd=path, capture_output=True, text=True, check=True
    )


def _call_tool(
    server: GitServer,
    tool_name: str,
    arguments: dict[str, Any],
    req_id: int = 1,
) -> dict[str, Any]:
    transport = server.get_inprocess_transport()
    transport.connect()
    req = JSONRPCRequest(
        method="tools/call",
        params={**make_envelope("test-agent"), "name": tool_name, "arguments": arguments},
        id=req_id,
    )
    resp = transport.send(req)
    if resp.is_error:
        raise RuntimeError(f"Tool call failed: {resp.error}")
    return resp.result


def _call_tool_error(
    server: GitServer,
    tool_name: str,
    arguments: dict[str, Any],
    req_id: int = 1,
) -> dict[str, Any]:
    transport = server.get_inprocess_transport()
    transport.connect()
    req = JSONRPCRequest(
        method="tools/call",
        params={**make_envelope("test-agent"), "name": tool_name, "arguments": arguments},
        id=req_id,
    )
    resp = transport.send(req)
    assert resp.is_error
    return resp.error


class TestGitServerBasic:
    def test_git_status_on_clean_repo(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(server, "git_status", {"path": str(tmp_path)})

        assert result["branch"] == "master" or result["branch"] == "main"
        assert result["changes"] == []
        assert isinstance(result["ahead"], int)
        assert isinstance(result["behind"], int)

    def test_git_status_with_changes(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "file1.txt", "hello", "first commit")
        (tmp_path / "file2.txt").write_text("uncommitted")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(server, "git_status", {"path": str(tmp_path)})

        assert len(result["changes"]) >= 1
        assert any(c["path"] == "file2.txt" for c in result["changes"])

    def test_git_log(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "a.txt", "a", "commit a")
        _make_commit(tmp_path, "b.txt", "b", "commit b")
        _make_commit(tmp_path, "c.txt", "c", "commit c")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(server, "git_log", {"path": str(tmp_path)})

        assert len(result["commits"]) == 3
        assert result["commits"][0]["message"] == "commit c"
        assert result["commits"][1]["message"] == "commit b"
        assert result["commits"][2]["message"] == "commit a"

    def test_git_log_with_max_count(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        for i in range(5):
            _make_commit(tmp_path, f"f{i}.txt", str(i), f"commit {i}")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(server, "git_log", {"path": str(tmp_path), "max_count": 2})

        assert len(result["commits"]) == 2
        assert result["commits"][0]["message"] == "commit 4"

    def test_git_log_commit_fields(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "x.txt", "x", "test commit")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(server, "git_log", {"path": str(tmp_path)})

        commit = result["commits"][0]
        assert len(commit["hash"]) == 40
        assert commit["author"] == "test"
        assert "test commit" in commit["message"]

    def test_git_branch(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "init.txt", "init", "initial commit")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(server, "git_branch", {"path": str(tmp_path)})

        assert len(result["branches"]) >= 1
        assert result["current"] in [b["name"] for b in result["branches"]]
        current_branch = [b for b in result["branches"] if b["current"]]
        assert len(current_branch) == 1

    def test_git_branch_with_multiple_branches(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "init.txt", "init", "initial commit")
        subprocess.run(
            ["git", "branch", "feature-branch"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(server, "git_branch", {"path": str(tmp_path)})

        branch_names = [b["name"] for b in result["branches"]]
        assert len(branch_names) >= 2
        assert "feature-branch" in branch_names

    def test_git_diff(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "first.txt", "first", "first commit")
        _make_commit(tmp_path, "second.txt", "second", "second commit")
        # Modify a tracked file to show in diff
        (tmp_path / "second.txt").write_text("modified content")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(server, "git_diff", {"path": str(tmp_path)})

        assert "second.txt" in result["diff"]
        assert result["files_changed"] >= 1


class TestGitServerSecurity:
    def test_path_outside_whitelist_blocked(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        whitelist = RepoWhitelist(["/nonexistent/path"])
        server = GitServer(repo_whitelist=whitelist)

        error = _call_tool_error(server, "git_status", {"path": str(tmp_path)})

        assert "whitelist" in error["message"].lower()

    def test_non_git_directory_returns_error(self, tmp_path: Path) -> None:
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        error = _call_tool_error(server, "git_status", {"path": str(tmp_path)})

        assert "not a git repository" in error["message"].lower()

    def test_empty_whitelist_blocks_all(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        whitelist = RepoWhitelist()
        server = GitServer(repo_whitelist=whitelist)

        error = _call_tool_error(server, "git_status", {"path": str(tmp_path)})

        assert "whitelist" in error["message"].lower()

    def test_write_operation_blocked_without_write_mode(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "init.txt", "init", "initial commit")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist, write_mode=False)

        error = _call_tool_error(
            server,
            "git_commit",
            {"path": str(tmp_path), "message": "should fail"},
        )

        assert "write mode" in error["message"].lower() or "disabled" in error["message"].lower()

    def test_commit_succeeds_with_write_mode(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "init.txt", "init", "initial commit")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist, write_mode=True)

        (tmp_path / "newfile.txt").write_text("new content")
        result = _call_tool(
            server,
            "git_commit",
            {"path": str(tmp_path), "message": "add newfile"},
        )

        assert result["success"] is True
        assert len(result["commit_hash"]) == 40

    def test_git_log_with_branch_param(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "init.txt", "init", "initial commit")
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        result = _call_tool(
            server,
            "git_log",
            {"path": str(tmp_path), "branch": current_branch},
        )

        assert len(result["commits"]) >= 1


class TestGitServerWriteMode:
    def test_commit_with_specific_files(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "init.txt", "init", "initial commit")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist, write_mode=True)

        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = _call_tool(
            server,
            "git_commit",
            {"path": str(tmp_path), "message": "add two files", "files": ["a.txt"]},
        )

        assert result["success"] is True
        log_result = _call_tool(server, "git_log", {"path": str(tmp_path)})
        assert any("add two files" in c["message"] for c in log_result["commits"])

    def test_push_blocked_without_write_mode(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist, write_mode=False)

        error = _call_tool_error(
            server,
            "git_push",
            {"path": str(tmp_path), "remote": "origin"},
        )

        assert "write mode" in error["message"].lower() or "disabled" in error["message"].lower()

    def test_write_mode_on_commit_makes_visible_commit(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist, write_mode=True)

        (tmp_path / "test.txt").write_text("content")
        _call_tool(
            server,
            "git_commit",
            {"path": str(tmp_path), "message": "test commit"},
        )

        log_result = _call_tool(server, "git_log", {"path": str(tmp_path)})
        assert len(log_result["commits"]) == 1
        assert log_result["commits"][0]["message"] == "test commit"

    def test_readonly_operations_work_without_write_mode(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "f.txt", "f", "first")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist, write_mode=False)

        status = _call_tool(server, "git_status", {"path": str(tmp_path)})
        log = _call_tool(server, "git_log", {"path": str(tmp_path)})
        branch = _call_tool(server, "git_branch", {"path": str(tmp_path)})
        diff = _call_tool(server, "git_diff", {"path": str(tmp_path)})

        assert status["branch"] != ""
        assert len(log["commits"]) == 1
        assert branch["current"] != ""
        assert isinstance(diff["files_changed"], int)


class TestCreateGitServerFactory:
    def test_create_git_server_defaults(self) -> None:
        server = create_git_server()
        assert isinstance(server, GitServer)
        assert server._write_mode is False
        assert len(server._whitelist.allowed_paths) == 0

    def test_create_git_server_with_whitelist(self) -> None:
        server = create_git_server(repo_whitelist=["/repo1", "/repo2"])
        assert isinstance(server, GitServer)
        assert "/repo1" in server._whitelist.allowed_paths
        assert "/repo2" in server._whitelist.allowed_paths

    def test_create_git_server_with_write_mode(self) -> None:
        server = create_git_server(write_mode=True)
        assert server._write_mode is True


class TestRepoWhitelist:
    def test_whitelist_exact_match(self, tmp_path: Path) -> None:
        path_str = str(tmp_path)
        wl = RepoWhitelist([path_str])
        assert wl.is_allowed(path_str) is True

    def test_whitelist_no_match(self) -> None:
        wl = RepoWhitelist(["/allowed/path"])
        assert wl.is_allowed("/other/path") is False

    def test_whitelist_empty_denies_all(self, tmp_path: Path) -> None:
        wl = RepoWhitelist()
        assert wl.is_allowed(str(tmp_path)) is False

    def test_whitelist_resolves_symlinks(self, tmp_path: Path) -> None:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        link_dir = tmp_path / "link"
        link_dir.symlink_to(real_dir)

        wl = RepoWhitelist([str(real_dir)])
        assert wl.is_allowed(str(link_dir)) is True

    def test_whitelist_allowed_paths_property(self) -> None:
        wl = RepoWhitelist(["/a", "/b"])
        paths = wl.allowed_paths
        assert len(paths) == 2
        assert wl.is_allowed("/a") is True
        assert wl.is_allowed("/b") is True


class TestGitServerMCPProtocol:
    def test_server_initialize(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(name="git-test", version="1.0.0", repo_whitelist=whitelist)

        transport = server.get_inprocess_transport()
        transport.connect()
        req = JSONRPCRequest(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            id=1,
        )
        resp = transport.send(req)
        assert not resp.is_error
        assert resp.result["serverInfo"]["name"] == "git-test"
        assert resp.result["serverInfo"]["version"] == "1.0.0"

    def test_tools_list(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        transport = server.get_inprocess_transport()
        transport.connect()
        req = JSONRPCRequest(method="tools/list", id=1)
        resp = transport.send(req)
        assert not resp.is_error
        tool_names = [t["name"] for t in resp.result["tools"]]
        expected = {"git_status", "git_log", "git_diff", "git_branch", "git_commit", "git_push"}
        assert set(tool_names) == expected

    def test_unknown_tool(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        transport = server.get_inprocess_transport()
        transport.connect()
        req = JSONRPCRequest(
            method="tools/call",
            params={**make_envelope("test-agent"), "name": "nonexistent", "arguments": {}},
            id=1,
        )
        resp = transport.send(req)
        assert resp.is_error
        assert resp.error_code == -32602


class TestGitServerDiffEdgeCases:
    def test_git_diff_with_base(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _make_commit(tmp_path, "a.txt", "a", "commit a")
        _make_commit(tmp_path, "b.txt", "b", "commit b")
        whitelist = RepoWhitelist([str(tmp_path)])
        server = GitServer(repo_whitelist=whitelist)

        log = _call_tool(server, "git_log", {"path": str(tmp_path)})
        first_hash = log["commits"][1]["hash"]

        result = _call_tool(
            server,
            "git_diff",
            {"path": str(tmp_path), "target": "HEAD", "base": first_hash},
        )

        assert result["files_changed"] >= 1
        assert "b.txt" in result["diff"]
