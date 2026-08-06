"""test_forensic — ForensicSnapshot 取证证据 bundle 测试

覆盖验收标准:
- 1.3-A1: ForensicSnapshot.snapshot(pid) 在 3 秒内产出 evidence bundle,体积 ≤ 50MB
- 1.3-A2: evidence bundle 的 HMAC 校验通过,任何篡改导致 verify()=False

使用 unittest.mock 模拟 psutil.Process,不依赖真实进程。
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from maref.sentinel.forensic import (
    _REDACTED_VALUE,
    EvidenceBundle,
    ForensicSnapshot,
    compute_bundle_hash,
)

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-forensic-hmac-key"


def _make_fake_process(pid: int = 12345) -> MagicMock:
    """构造一个 fake psutil.Process,带完整属性"""
    proc = MagicMock()
    proc.pid = pid
    proc.name.return_value = "test-agent"
    proc.exe.return_value = "/usr/bin/python3"
    proc.cwd.return_value = "/tmp/work"
    proc.cmdline.return_value = ["python3", "-m", "maref"]
    proc.username.return_value = "testuser"
    proc.create_time.return_value = 1000000.0
    proc.status.return_value = "running"
    proc.ppid.return_value = 1
    proc.num_fds.return_value = 5
    proc.num_threads.return_value = 3
    proc.cpu_percent.return_value = 12.5
    proc.cpu_affinity.return_value = [0, 1]

    # memory_info
    mem_info = MagicMock()
    mem_info.rss = 1024000
    mem_info.vms = 2048000
    proc.memory_info.return_value = mem_info

    # open_files
    f1 = MagicMock()
    f1.path = "/tmp/work/data.txt"
    f1.fd = 3
    f1.position = 0
    f1.mode = "r"
    f2 = MagicMock()
    f2.path = "/tmp/work/log.txt"
    f2.fd = 4
    f2.position = 1024
    f2.mode = "a"
    proc.open_files.return_value = [f1, f2]

    # connections
    conn = MagicMock()
    conn.family = 2  # AF_INET
    conn.type = 1  # SOCK_STREAM
    conn.status = "ESTABLISHED"
    laddr = MagicMock()
    laddr.ip = "127.0.0.1"
    laddr.port = 8080
    raddr = MagicMock()
    raddr.ip = "10.0.0.1"
    raddr.port = 443
    conn.laddr = laddr
    conn.raddr = raddr
    conn.fd = 5
    proc.connections.return_value = [conn]

    # memory_maps
    m = MagicMock()
    m.addr = "00400000-00500000"
    m.perm = "r-xp"
    m.path = "/usr/bin/python3"
    m.rss = 1024
    m.private = 512
    proc.memory_maps.return_value = [m]

    # environ
    proc.environ.return_value = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp/home",
        "ANTHROPIC_API_KEY": "sk-ant-super-secret",
        "OPENAI_API_KEY": "sk-openai-secret",
        "MY_CUSTOM_TOKEN": "tok-xyz",
        "MY_DB_PASSWORD": "hunter2",
        "NORMAL_VAR": "normal-value",
    }

    return proc


class TestEvidenceBundle:
    """EvidenceBundle 数据类测试"""

    def test_default_values(self) -> None:
        bundle = EvidenceBundle()
        assert bundle.bundle_id  # UUID 自动生成
        assert bundle.pid == 0
        assert bundle.process_info == {}
        assert bundle.hmac_signature == ""

    def test_with_hash_returns_new_instance(self) -> None:
        bundle = EvidenceBundle(pid=1234)
        signed = bundle.with_hash(HMAC_KEY)
        assert signed is not bundle
        assert signed.pid == 1234
        assert signed.hmac_signature != ""

    def test_verify_valid_signature(self) -> None:
        bundle = EvidenceBundle(pid=1234, agent_id="agent-1").with_hash(HMAC_KEY)
        assert bundle.verify(HMAC_KEY) is True

    def test_verify_no_signature_returns_false(self) -> None:
        bundle = EvidenceBundle(pid=1234)
        assert bundle.verify(HMAC_KEY) is False

    def test_verify_tampered_bundle_returns_false(self) -> None:
        """1.3-A2: 篡改导致 verify()=False"""
        bundle = EvidenceBundle(pid=1234, agent_id="agent-1").with_hash(HMAC_KEY)
        # 篡改 pid (frozen dataclass 需用 replace)
        from dataclasses import replace

        tampered = replace(bundle, pid=9999)
        assert tampered.verify(HMAC_KEY) is False

    def test_verify_tampered_evidence_returns_false(self) -> None:
        """篡改 evidence 字段导致 verify()=False"""
        bundle = EvidenceBundle(
            pid=1234,
            process_info={"name": "agent"},
        ).with_hash(HMAC_KEY)
        from dataclasses import replace

        tampered = replace(
            bundle, process_info={"name": "tampered-evil-agent"}
        )
        assert tampered.verify(HMAC_KEY) is False

    def test_to_audit_payload_excludes_signature(self) -> None:
        bundle = EvidenceBundle(pid=1234, agent_id="agent-1").with_hash(HMAC_KEY)
        payload = bundle.to_audit_payload()
        assert "hmac_signature" not in payload
        assert payload["pid"] == 1234
        assert payload["agent_id"] == "agent-1"

    def test_compute_bundle_hash_deterministic(self) -> None:
        """相同内容产生相同 hash"""
        b1 = EvidenceBundle(pid=1, agent_id="a", captured_at=1000.0)
        b2 = EvidenceBundle(
            bundle_id=b1.bundle_id, pid=1, agent_id="a", captured_at=1000.0
        )
        h1 = compute_bundle_hash(b1, HMAC_KEY)
        h2 = compute_bundle_hash(b2, HMAC_KEY)
        assert h1 == h2


class TestForensicSnapshotCapture:
    """ForensicSnapshot.snapshot() 采集测试 — 覆盖 1.3-A1"""

    async def test_snapshot_returns_signed_bundle(self) -> None:
        """snapshot() 返回带 HMAC 签名的 EvidenceBundle"""
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process(pid=12345)

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345, trigger_event_id="evt-001")

        assert bundle.pid == 12345
        assert bundle.trigger_event_id == "evt-001"
        assert bundle.hmac_signature != ""
        assert bundle.verify(HMAC_KEY) is True

    async def test_snapshot_captures_process_info(self) -> None:
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process(pid=12345)

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        info = bundle.process_info
        assert info["pid"] == 12345
        assert info["name"] == "test-agent"
        assert info["exe"] == "/usr/bin/python3"
        assert info["cmdline"] == ["python3", "-m", "maref"]
        assert info["username"] == "testuser"
        assert info["status"] == "running"
        assert info["ppid"] == 1
        assert info["num_fds"] == 5
        assert info["num_threads"] == 3
        assert info["memory_rss"] == 1024000
        assert info["memory_vms"] == 2048000

    async def test_snapshot_captures_open_files(self) -> None:
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process(pid=12345)

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        assert len(bundle.open_files) == 2
        assert bundle.open_files[0]["path"] == "/tmp/work/data.txt"
        assert bundle.open_files[0]["fd"] == 3
        assert bundle.open_files[1]["path"] == "/tmp/work/log.txt"

    async def test_snapshot_captures_connections(self) -> None:
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process(pid=12345)

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        assert len(bundle.network_connections) == 1
        conn = bundle.network_connections[0]
        assert conn["status"] == "ESTABLISHED"
        assert conn["laddr"]["ip"] == "127.0.0.1"
        assert conn["laddr"]["port"] == 8080
        assert conn["raddr"]["ip"] == "10.0.0.1"
        assert conn["raddr"]["port"] == 443

    async def test_snapshot_captures_memory_maps(self) -> None:
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process(pid=12345)

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        assert len(bundle.memory_maps) == 1
        m = bundle.memory_maps[0]
        assert m["addr"] == "00400000-00500000"
        assert m["perm"] == "r-xp"
        assert m["path"] == "/usr/bin/python3"

    async def test_snapshot_redacts_sensitive_env_vars(self) -> None:
        """敏感环境变量自动脱敏"""
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process(pid=12345)

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        env = bundle.environment
        # 显式名单的敏感变量
        assert env["ANTHROPIC_API_KEY"] == _REDACTED_VALUE
        assert env["OPENAI_API_KEY"] == _REDACTED_VALUE
        # 模式匹配的敏感变量
        assert env["MY_CUSTOM_TOKEN"] == _REDACTED_VALUE
        assert env["MY_DB_PASSWORD"] == _REDACTED_VALUE
        # 非敏感变量保留原值
        assert env["PATH"] == "/usr/bin:/bin"
        assert env["HOME"] == "/tmp/home"
        assert env["NORMAL_VAR"] == "normal-value"

    async def test_snapshot_within_3_seconds(self) -> None:
        """1.3-A1: snapshot(pid) 在 3 秒内完成"""
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process(pid=12345)

        with patch("psutil.Process", return_value=fake_proc):
            start = time.monotonic()
            bundle = await snapshotter.snapshot(pid=12345)
            elapsed = time.monotonic() - start

        assert elapsed < 3.0, f"snapshot took {elapsed:.2f}s, expected < 3s"
        assert bundle.verify(HMAC_KEY) is True

    async def test_snapshot_handles_nonexistent_process(self) -> None:
        """进程不存在时返回部分快照,不抛异常"""
        import psutil

        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)

        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(99999)):
            bundle = await snapshotter.snapshot(pid=99999)

        # 即使进程不存在也返回 bundle (部分快照)
        assert bundle.pid == 99999
        assert bundle.process_info.get("error") == "process_unavailable"
        assert bundle.open_files == []
        assert bundle.network_connections == []
        assert bundle.memory_maps == []
        assert bundle.environment == {}
        # HMAC 仍然有效
        assert bundle.verify(HMAC_KEY) is True

    async def test_snapshot_handles_access_denied(self) -> None:
        """权限不足时返回部分快照"""
        import psutil

        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)

        with patch("psutil.Process", side_effect=psutil.AccessDenied(12345)):
            bundle = await snapshotter.snapshot(pid=12345)

        assert bundle.pid == 12345
        assert bundle.process_info.get("error") == "process_unavailable"
        assert bundle.verify(HMAC_KEY) is True


class TestForensicSnapshotTruncation:
    """bundle 体积上限保护测试"""

    async def test_open_files_truncated(self) -> None:
        """open_files 超过上限时截断并记录 _truncated"""
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY, max_open_files=5)
        fake_proc = _make_fake_process()
        # 构造 10 个 open_files
        fake_proc.open_files.return_value = [
            MagicMock(path=f"/tmp/f{i}.txt", fd=i, position=0, mode="r")
            for i in range(10)
        ]

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        # 5 条记录 + 1 条 _truncated 标记
        assert len(bundle.open_files) == 6
        assert bundle.open_files[-1].get("_truncated") == 5

    async def test_connections_truncated(self) -> None:
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY, max_connections=3)
        fake_proc = _make_fake_process()
        fake_proc.connections.return_value = [
            MagicMock(
                family=2, type=1, status="ESTABLISHED",
                laddr=MagicMock(ip="127.0.0.1", port=8000 + i),
                raddr=MagicMock(ip="10.0.0.1", port=443),
                fd=5 + i,
            )
            for i in range(10)
        ]

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        assert len(bundle.network_connections) == 4  # 3 + truncated
        assert bundle.network_connections[-1].get("_truncated") == 7

    async def test_memory_maps_truncated(self) -> None:
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY, max_memory_maps=3)
        fake_proc = _make_fake_process()
        fake_proc.memory_maps.return_value = [
            MagicMock(
                addr=f"00{i}00000-00{i + 1}00000",
                perm="r-xp", path=f"/lib/lib{i}.so",
                rss=1024, private=512,
            )
            for i in range(10)
        ]

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        assert len(bundle.memory_maps) == 4  # 3 + truncated
        assert bundle.memory_maps[-1].get("_truncated") == 7


class TestForensicSnapshotAgent:
    """snapshot_agent() 多进程取证测试"""

    async def test_snapshot_agent_no_resolver_returns_empty(self) -> None:
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        bundles = await snapshotter.snapshot_agent("agent-1")
        assert bundles == []

    async def test_snapshot_agent_with_resolver(self) -> None:
        """agent_pid_resolver 返回多个 PID,并行取证"""
        async def resolver(agent_id: str) -> list[int]:
            return [100, 200, 300]

        snapshotter = ForensicSnapshot(
            hmac_key=HMAC_KEY, agent_pid_resolver=resolver
        )
        fake_proc = _make_fake_process()

        with patch("psutil.Process", return_value=fake_proc):
            bundles = await snapshotter.snapshot_agent("agent-multi")

        assert len(bundles) == 3
        pids = {b.pid for b in bundles}
        assert pids == {100, 200, 300}
        for b in bundles:
            assert b.verify(HMAC_KEY) is True
            assert b.trigger_event_id == "agent:agent-multi"

    async def test_snapshot_agent_sync_resolver(self) -> None:
        """同步 resolver (返回 list 而非 coroutine) 也能工作"""
        def resolver(agent_id: str) -> list[int]:
            return [100, 200]

        snapshotter = ForensicSnapshot(
            hmac_key=HMAC_KEY, agent_pid_resolver=resolver
        )
        fake_proc = _make_fake_process()

        with patch("psutil.Process", return_value=fake_proc):
            bundles = await snapshotter.snapshot_agent("agent-sync")

        assert len(bundles) == 2

    async def test_snapshot_agent_resolver_error_returns_empty(self) -> None:
        async def resolver(agent_id: str) -> list[int]:
            raise RuntimeError("resolver failed")

        snapshotter = ForensicSnapshot(
            hmac_key=HMAC_KEY, agent_pid_resolver=resolver
        )
        bundles = await snapshotter.snapshot_agent("agent-err")
        assert bundles == []

    async def test_snapshot_agent_empty_pids_returns_empty(self) -> None:
        async def resolver(agent_id: str) -> list[int]:
            return []

        snapshotter = ForensicSnapshot(
            hmac_key=HMAC_KEY, agent_pid_resolver=resolver
        )
        bundles = await snapshotter.snapshot_agent("agent-empty")
        assert bundles == []


class TestForensicSnapshotVerify:
    """verify_bundle() 测试 — 覆盖 1.3-A2"""

    async def test_verify_bundle_valid(self) -> None:
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process()

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        assert snapshotter.verify_bundle(bundle) is True

    async def test_verify_bundle_tampered(self) -> None:
        """1.3-A2: 篡改导致 verify_bundle()=False"""
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process()

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        from dataclasses import replace

        tampered = replace(bundle, pid=99999)
        assert snapshotter.verify_bundle(tampered) is False

    async def test_verify_bundle_wrong_key(self) -> None:
        """用错误的 key 验证返回 False"""
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process()

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        wrong_key_snapshotter = ForensicSnapshot(hmac_key=b"wrong-key")
        assert wrong_key_snapshotter.verify_bundle(bundle) is False


class TestForensicSnapshotSensitiveEnv:
    """敏感环境变量脱敏测试"""

    async def test_custom_sensitive_env_vars_merged(self) -> None:
        """自定义敏感变量与默认名单合并"""
        snapshotter = ForensicSnapshot(
            hmac_key=HMAC_KEY,
            sensitive_env_vars=("MY_CUSTOM_SECRET_VAR",),
        )
        fake_proc = _make_fake_process()
        fake_proc.environ.return_value = {
            "MY_CUSTOM_SECRET_VAR": "custom-secret",
            "NORMAL": "ok",
        }

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        assert bundle.environment["MY_CUSTOM_SECRET_VAR"] == _REDACTED_VALUE
        assert bundle.environment["NORMAL"] == "ok"

    async def test_pattern_based_redaction(self) -> None:
        """模式匹配脱敏 (*KEY / *SECRET / *TOKEN / *PASSWORD)"""
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY)
        fake_proc = _make_fake_process()
        fake_proc.environ.return_value = {
            "API_KEY": "k1",
            "DB_SECRET": "s1",
            "AUTH_TOKEN": "t1",
            "USER_PASSWORD": "p1",
            "PRIVATE_KEY": "pk1",
            "CREDENTIAL": "c1",
            "NORMAL_VAR": "ok",
        }

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        env = bundle.environment
        assert env["API_KEY"] == _REDACTED_VALUE
        assert env["DB_SECRET"] == _REDACTED_VALUE
        assert env["AUTH_TOKEN"] == _REDACTED_VALUE
        assert env["USER_PASSWORD"] == _REDACTED_VALUE
        assert env["PRIVATE_KEY"] == _REDACTED_VALUE
        assert env["CREDENTIAL"] == _REDACTED_VALUE
        assert env["NORMAL_VAR"] == "ok"

    async def test_env_var_truncation(self) -> None:
        """环境变量数超限时截断"""
        snapshotter = ForensicSnapshot(hmac_key=HMAC_KEY, max_env_vars=3)
        fake_proc = _make_fake_process()
        fake_proc.environ.return_value = {
            f"VAR_{i}": str(i) for i in range(10)
        }

        with patch("psutil.Process", return_value=fake_proc):
            bundle = await snapshotter.snapshot(pid=12345)

        # 3 条 + _truncated 标记
        assert len(bundle.environment) == 4
        assert "_truncated" in bundle.environment
