"""test_probes — 4 个 psutil Probe 检测逻辑测试

覆盖验收标准:
- 1.1-A2: TimezoneProbe 对 /etc/localtime 读取行为检出率 ≥ 95%
- 1.1-A3: EnvProbe 对 ANTHROPIC_BASE_URL 读取行为检出率 ≥ 95%
- 1.1-A4: ProcessProbe 对 ptrace/SYS_ptrace 等调试器附加行为检出率 ≥ 90%

使用 unittest.mock 模拟 psutil.Process 行为,不依赖真实进程。
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maref.sentinel.event import AttackType, Severity
from maref.sentinel.probes.base import ProbeConfig
from maref.sentinel.probes.env_probe import EnvProbe
from maref.sentinel.probes.file_probe import FileProbe
from maref.sentinel.probes.process_probe import ProcessProbe
from maref.sentinel.probes.timezone_probe import TimezoneProbe

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-probe-hmac-key"


def _make_config(**kwargs: Any) -> ProbeConfig:
    """创建测试用 ProbeConfig"""
    defaults: dict[str, Any] = {
        "poll_interval": 0.01,
        "target_pids": (999999,),  # 不存在的 PID,避免误检
        "hmac_key": HMAC_KEY,
    }
    defaults.update(kwargs)
    return ProbeConfig(**defaults)


class TestProcessProbe:
    """ProcessProbe 测试 — 覆盖 1.1-A4 (ptrace 检测)"""

    async def test_probe_name(self) -> None:
        probe = ProcessProbe(_make_config())
        assert probe.probe_name == "process"

    async def test_start_stop_idempotent(self) -> None:
        probe = ProcessProbe(_make_config())
        await probe.start()
        assert probe._started is True
        await probe.start()  # 幂等
        assert probe._started is True
        await probe.stop()
        assert probe._started is False

    async def test_ptrace_detection_linux(self) -> None:
        """1.1-A4: ptrace 检测 — Linux /proc/<pid>/status TracerPid != 0"""
        probe = ProcessProbe(_make_config(target_pids=(1,)))

        # 模拟 /proc/1/status 含 TracerPid: 999
        fake_status_content = "Name:	test\nTracerPid:\t999\n"

        # patch asyncio.to_thread → 同步执行,避免子线程中 mock 不生效
        sync_to_thread = lambda fn, *args, **kw: fn(*args)
        with patch("os.path.exists", return_value=True), \
                patch("builtins.open",
                      return_value=MagicMock(read=MagicMock(return_value=fake_status_content)),
                      create=True), \
                patch("maref.sentinel.probes.process_probe.asyncio.to_thread",
                      side_effect=sync_to_thread):
            # 同时 mock psutil.Process
            with patch("psutil.Process") as mock_proc_cls:
                mock_proc = MagicMock()
                mock_proc.children.return_value = []
                mock_proc.status.return_value = "running"
                mock_proc_cls.return_value = mock_proc

                await probe.start()
                events = await probe.poll()
                await probe.stop()

        # 应该检出 ptrace 附加
        ptrace_events = [
            e for e in events
            if e.evidence.get("detection") == "ptrace_attached"
        ]
        assert len(ptrace_events) >= 1
        assert ptrace_events[0].severity == Severity.CRITICAL
        assert ptrace_events[0].attack_type == AttackType.PRIVILEGE_ABUSE
        assert ptrace_events[0].evidence["tracer_pid"] == 999

    async def test_no_ptrace_when_tracer_pid_zero(self) -> None:
        """TracerPid=0 → 不告警"""
        probe = ProcessProbe(_make_config(target_pids=(1,)))

        fake_status_content = "Name:	test\nTracerPid:\t0\n"

        # patch asyncio.to_thread → 同步执行
        sync_to_thread = lambda fn, *args, **kw: fn(*args)
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", create=True) as mock_open, \
             patch("maref.sentinel.probes.process_probe.asyncio.to_thread",
                   side_effect=sync_to_thread):
            # open(...).read() 不走 with 语句
            mock_open.return_value.read.return_value = fake_status_content
            with patch("psutil.Process") as mock_proc_cls:
                mock_proc = MagicMock()
                mock_proc.children.return_value = []
                mock_proc.status.return_value = "running"
                mock_proc_cls.return_value = mock_proc

                await probe.start()
                events = await probe.poll()
                await probe.stop()

        ptrace_events = [
            e for e in events
            if e.evidence.get("detection") == "ptrace_attached"
        ]
        assert len(ptrace_events) == 0

    async def test_suspicious_debugger_child_detection(self) -> None:
        """检测 Agent 启动 gdb 等调试器子进程"""
        probe = ProcessProbe(_make_config(target_pids=(1,)))

        mock_child = MagicMock()
        mock_child.pid = 12345
        mock_child.name.return_value = "gdb"

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            # start() 时无子进程,子进程在 poll() 时新增
            mock_proc.children.return_value = []
            mock_proc.status.return_value = "running"
            mock_proc_cls.return_value = mock_proc

            with patch("os.path.exists", return_value=False):  # 非 Linux
                await probe.start()
                # poll() 时出现 gdb 子进程
                mock_proc.children.return_value = [mock_child]
                events = await probe.poll()
                await probe.stop()

        debugger_events = [
            e for e in events
            if e.evidence.get("detection") == "suspicious_debugger_child"
        ]
        assert len(debugger_events) >= 1
        assert debugger_events[0].severity == Severity.CRITICAL
        assert debugger_events[0].evidence["child_name"] == "gdb"

    async def test_event_hmac_signed(self) -> None:
        """所有事件必须带 HMAC 签名"""
        probe = ProcessProbe(_make_config(target_pids=(1,)))

        mock_child = MagicMock()
        mock_child.pid = 12345
        mock_child.name.return_value = "strace"

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.children.return_value = [mock_child]
            mock_proc.status.return_value = "running"
            mock_proc_cls.return_value = mock_proc

            with patch("os.path.exists", return_value=False):
                await probe.start()
                events = await probe.poll()
                await probe.stop()

        for event in events:
            assert event.hash, "Event must have HMAC hash"
            assert len(event.hash) == 64, "HMAC-SHA256 must be 64 hex chars"


class TestEnvProbe:
    """EnvProbe 测试 — 覆盖 1.1-A3 (ANTHROPIC_BASE_URL 检测)"""

    async def test_probe_name(self) -> None:
        probe = EnvProbe(_make_config())
        assert probe.probe_name == "env"

    async def test_anthropic_base_url_detection(self) -> None:
        """1.1-A3: ANTHROPIC_BASE_URL 环境变量检测"""
        config = _make_config(target_pids=(1,))
        probe = EnvProbe(config)

        # 模拟进程 environ 含 ANTHROPIC_BASE_URL
        fake_environ = {"ANTHROPIC_BASE_URL": "https://proxy.example.com", "PATH": "/usr/bin"}

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.environ.return_value = fake_environ
            mock_proc_cls.return_value = mock_proc

            await probe.start()
            # start() 时基线应该记录了 ANTHROPIC_BASE_URL (因为是新的)
            # 第二次 poll() 应该不报 (因为已经在基线中)
            # 但第一次 poll() 之后的基线更新会让 is_new=False
            # 所以我们需要让 start() 时基线为空,poll() 时 environ 含新变量

        # 重新测试: start() 时 environ 不含 ANTHROPIC_BASE_URL
        probe2 = EnvProbe(config)

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()

            # start() 时返回空 environ
            mock_proc.environ.return_value = {}
            mock_proc_cls.return_value = mock_proc
            await probe2.start()

            # poll() 时返回含 ANTHROPIC_BASE_URL 的 environ
            mock_proc.environ.return_value = {
                "ANTHROPIC_BASE_URL": "https://proxy.example.com"
            }
            events = await probe2.poll()
            await probe2.stop()

        env_events = [
            e for e in events
            if e.evidence.get("detection") == "sensitive_env_var"
            and e.evidence.get("var_name") == "ANTHROPIC_BASE_URL"
        ]
        assert len(env_events) >= 1
        assert env_events[0].severity == Severity.HIGH
        assert env_events[0].attack_type == AttackType.ENV_EXFIL
        # 不应该记录明文 value
        assert "value" not in env_events[0].evidence
        assert "value_hash" in env_events[0].evidence

    async def test_api_key_detection_critical(self) -> None:
        """API key 环境变量 → CRITICAL"""
        config = _make_config(target_pids=(1,))
        probe = EnvProbe(config)

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.environ.return_value = {}
            mock_proc_cls.return_value = mock_proc
            await probe.start()
            mock_proc.environ.return_value = {"ANTHROPIC_API_KEY": "sk-ant-xxx"}
            events = await probe.poll()
            await probe.stop()

        critical_events = [
            e for e in events
            if e.severity == Severity.CRITICAL
            and e.evidence.get("var_name") == "ANTHROPIC_API_KEY"
        ]
        assert len(critical_events) >= 1

    async def test_no_event_when_baseline_matches(self) -> None:
        """环境变量无变化 → 不告警"""
        config = _make_config(target_pids=(1,))
        probe = EnvProbe(config)
        fake_environ = {"PATH": "/usr/bin", "HOME": "/root"}

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.environ.return_value = fake_environ
            mock_proc_cls.return_value = mock_proc

            await probe.start()
            events = await probe.poll()  # environ 没变
            await probe.stop()

        # PATH/HOME 不是敏感变量,且无变化
        sensitive_events = [
            e for e in events
            if e.evidence.get("detection") == "sensitive_env_var"
        ]
        assert len(sensitive_events) == 0


class TestFileProbe:
    """FileProbe 测试"""

    async def test_probe_name(self) -> None:
        probe = FileProbe(_make_config())
        assert probe.probe_name == "file"

    async def test_ssh_key_detection(self) -> None:
        """检测 SSH 私钥访问 → CRITICAL"""
        config = _make_config(
            target_pids=(1,),
            sensitive_paths=("~/.ssh/id_rsa",),
        )
        probe = FileProbe(config)

        ssh_path = os.path.expanduser("~/.ssh/id_rsa")

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()

            # start() 时无打开文件
            mock_proc.open_files.return_value = []
            mock_proc_cls.return_value = mock_proc
            await probe.start()

            # poll() 时打开了 SSH 私钥
            from collections import namedtuple
            OpenFile = namedtuple("OpenFile", ["path", "fd"])
            mock_proc.open_files.return_value = [OpenFile(path=ssh_path, fd=3)]

            events = await probe.poll()
            await probe.stop()

        ssh_events = [
            e for e in events
            if "id_rsa" in e.evidence.get("file_path", "")
        ]
        assert len(ssh_events) >= 1
        assert ssh_events[0].severity == Severity.CRITICAL
        assert ssh_events[0].attack_type == AttackType.PRIVILEGE_ABUSE

    async def test_no_event_for_non_sensitive_file(self) -> None:
        """非敏感文件 → 不告警"""
        config = _make_config(target_pids=(1,))
        probe = FileProbe(config)

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.open_files.return_value = []
            mock_proc_cls.return_value = mock_proc
            await probe.start()

            from collections import namedtuple
            OpenFile = namedtuple("OpenFile", ["path", "fd"])
            mock_proc.open_files.return_value = [
                OpenFile(path="/tmp/non_sensitive.txt", fd=3)
            ]
            events = await probe.poll()
            await probe.stop()

        assert len(events) == 0


class TestTimezoneProbe:
    """TimezoneProbe 测试 — 覆盖 1.1-A2 (/etc/localtime 检测)"""

    async def test_probe_name(self) -> None:
        probe = TimezoneProbe(_make_config())
        assert probe.probe_name == "timezone"

    async def test_localtime_open_detection(self) -> None:
        """1.1-A2: /etc/localtime 打开检测 → CRITICAL"""
        config = _make_config(target_pids=(1,))
        probe = TimezoneProbe(config)

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()

            # start() 时无打开文件
            mock_proc.open_files.return_value = []
            mock_proc.memory_maps.return_value = []
            mock_proc.environ.return_value = {}
            mock_proc_cls.return_value = mock_proc
            await probe.start()

            # poll() 时打开了 /etc/localtime
            from collections import namedtuple
            OpenFile = namedtuple("OpenFile", ["path", "fd"])
            mock_proc.open_files.return_value = [
                OpenFile(path="/etc/localtime", fd=3)
            ]
            events = await probe.poll()
            await probe.stop()

        tz_events = [
            e for e in events
            if e.attack_type == AttackType.SILENT_TIMEZONE
        ]
        assert len(tz_events) >= 1
        assert tz_events[0].severity == Severity.CRITICAL
        assert tz_events[0].evidence["file_path"] == "/etc/localtime"
        assert tz_events[0].evidence["detection_method"] == "open_files"

    async def test_zoneinfo_memory_map_detection(self) -> None:
        """zoneinfo 内存映射检测 → HIGH"""
        config = _make_config(target_pids=(1,))
        probe = TimezoneProbe(config)

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.open_files.return_value = []
            mock_proc.memory_maps.return_value = []
            mock_proc.environ.return_value = {}
            mock_proc_cls.return_value = mock_proc
            await probe.start()

            from collections import namedtuple
            MMap = namedtuple("MMap", ["path", "rss", "addr", "perm"])
            mock_proc.memory_maps.return_value = [
                MMap(path="/usr/share/zoneinfo/Asia/Shanghai", rss=4096, addr="0x7f00", perm="r--"),
            ]
            events = await probe.poll()
            await probe.stop()

        tz_events = [
            e for e in events
            if e.evidence.get("detection_method") == "memory_maps"
        ]
        assert len(tz_events) >= 1
        assert tz_events[0].severity == Severity.HIGH

    async def test_tz_env_var_asian_detection(self) -> None:
        """TZ=Asia/Shanghai 环境变量检测 → HIGH"""
        config = _make_config(target_pids=(1,))
        probe = TimezoneProbe(config)

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.open_files.return_value = []
            mock_proc.memory_maps.return_value = []
            mock_proc.environ.return_value = {}
            mock_proc_cls.return_value = mock_proc
            await probe.start()

            mock_proc.environ.return_value = {"TZ": "Asia/Shanghai"}
            events = await probe.poll()
            await probe.stop()

        tz_events = [
            e for e in events
            if e.evidence.get("detection") == "tz_env_var_asian"
        ]
        assert len(tz_events) >= 1
        assert tz_events[0].severity == Severity.HIGH
        assert tz_events[0].evidence["tz_value"] == "Asia/Shanghai"

    async def test_tz_env_var_non_asian_no_alert(self) -> None:
        """TZ=America/New_York → 不告警 (非亚洲时区)"""
        config = _make_config(target_pids=(1,))
        probe = TimezoneProbe(config)

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.open_files.return_value = []
            mock_proc.memory_maps.return_value = []
            mock_proc.environ.return_value = {}
            mock_proc_cls.return_value = mock_proc
            await probe.start()

            mock_proc.environ.return_value = {"TZ": "America/New_York"}
            events = await probe.poll()
            await probe.stop()

        tz_events = [
            e for e in events
            if e.evidence.get("detection") == "tz_env_var_asian"
        ]
        assert len(tz_events) == 0

    async def test_event_hmac_signed(self) -> None:
        """所有事件必须带 HMAC 签名"""
        config = _make_config(target_pids=(1,))
        probe = TimezoneProbe(config)

        with patch("psutil.Process") as mock_proc_cls:
            mock_proc = MagicMock()
            mock_proc.open_files.return_value = []
            mock_proc.memory_maps.return_value = []
            mock_proc.environ.return_value = {}
            mock_proc_cls.return_value = mock_proc
            await probe.start()

            from collections import namedtuple
            OpenFile = namedtuple("OpenFile", ["path", "fd"])
            mock_proc.open_files.return_value = [
                OpenFile(path="/etc/localtime", fd=3)
            ]
            events = await probe.poll()
            await probe.stop()

        for event in events:
            assert event.hash, "Event must have HMAC hash"
            assert len(event.hash) == 64


class TestProbeHealthCheck:
    """Probe 健康检查测试"""

    async def test_process_probe_health_check(self) -> None:
        probe = ProcessProbe(_make_config())
        await probe.start()
        healthy = await probe.health_check()
        assert healthy is True
        await probe.stop()

    async def test_env_probe_health_check(self) -> None:
        probe = EnvProbe(_make_config())
        await probe.start()
        healthy = await probe.health_check()
        # health_check 默认返回 True
        assert healthy is True
        await probe.stop()
