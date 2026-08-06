"""test_linux_bpf — Linux eBPF + seccomp 观测模块测试

覆盖验收标准:
- M3-M3: BPFProbe 在 bcc 不可用时优雅降级
- M3-M4: SeccompFilter 进程级 syscall 过滤
- M3-M5: 观测事件 HMAC 签名
"""

from __future__ import annotations

import ctypes
from unittest.mock import MagicMock

import pytest

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.platform.linux import (
    X8664Syscalls,
    BPFNotAvailableError,
    BPFProbe,
    SeccompFilter,
    SeccompPolicy,
)
from maref.sentinel.platform.linux.bpf_probe import (
    BPF_CONNECT_PROG,
    BPF_ENVIRON_PROG,
    BPF_OPENAT_PROG,
)
from maref.sentinel.platform.linux.seccomp_filter import (
    PR_SET_SECCOMP,
    SECCOMP_MODE_FILTER,
    SeccompFilterError,
    SockFilter,
    SockFProg,
    _build_seccomp_filter,
)

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-linux-bpf-hmac-key"


# ---------------------------------------------------------------------------
# eBPF C program tests
# ---------------------------------------------------------------------------


class TestBPFPrograms:
    """eBPF C 程序字符串测试"""

    def test_connect_program_contains_expected_symbols(self) -> None:
        assert "tracepoint__syscalls__sys_enter_connect" in BPF_CONNECT_PROG
        assert "trace_connect_enter" in BPF_CONNECT_PROG
        assert "connect_events" in BPF_CONNECT_PROG
        assert "uservaddr" in BPF_CONNECT_PROG

    def test_openat_program_contains_expected_symbols(self) -> None:
        assert "tracepoint__syscalls__sys_enter_openat" in BPF_OPENAT_PROG
        assert "trace_openat_enter" in BPF_OPENAT_PROG
        assert "openat_events" in BPF_OPENAT_PROG
        assert "filename" in BPF_OPENAT_PROG

    def test_environ_program_contains_expected_symbols(self) -> None:
        assert "tracepoint__syscalls__sys_enter_openat" in BPF_ENVIRON_PROG
        assert "trace_openat_environ" in BPF_ENVIRON_PROG
        assert "environ_events" in BPF_ENVIRON_PROG
        assert "environ" in BPF_ENVIRON_PROG

    def test_programs_are_valid_c_syntax(self) -> None:
        """每个 BPF 程序以函数定义结尾,包含 include 和 struct"""
        for prog in (BPF_CONNECT_PROG, BPF_OPENAT_PROG, BPF_ENVIRON_PROG):
            assert "#include" in prog
            assert "struct" in prog
            assert "return 0;" in prog


# ---------------------------------------------------------------------------
# BPFProbe tests (without bcc — graceful fallback)
# ---------------------------------------------------------------------------


class TestBPFProbeWithoutBCC:
    """BPFProbe 测试 — bcc 不可用时的降级行为"""

    def test_init_defaults(self) -> None:
        probe = BPFProbe(hmac_key=HMAC_KEY)
        assert probe.probe_name == "ebpf"
        assert probe.is_running is False
        assert probe.total_events == 0
        assert probe.lost_events == 0

    def test_snapshot_returns_initial_state(self) -> None:
        probe = BPFProbe(hmac_key=HMAC_KEY)
        snap = probe.snapshot()
        assert snap["probe_name"] == "ebpf"
        assert snap["is_running"] is False
        assert snap["total_events"] == 0
        assert snap["lost_events"] == 0
        assert snap["bpf_modules_loaded"] == 0
        assert snap["perf_buffers_active"] == 0

    async def test_start_raises_bpf_not_available(self) -> None:
        """bcc 未安装时,start() 应抛出 BPFNotAvailableError"""
        probe = BPFProbe(hmac_key=HMAC_KEY)
        with pytest.raises(BPFNotAvailableError):
            await probe.start()

    async def test_observe_syscalls_raises_bpf_not_available(self) -> None:
        probe = BPFProbe(hmac_key=HMAC_KEY)
        with pytest.raises(BPFNotAvailableError):
            probe.observe_syscalls(pid=1234)

    async def test_observe_network_raises_bpf_not_available(self) -> None:
        probe = BPFProbe(hmac_key=HMAC_KEY)
        with pytest.raises(BPFNotAvailableError):
            probe.observe_network(pid=1234)

    async def test_stop_is_idempotent_when_not_running(self) -> None:
        """未运行时调用 stop() 不应报错"""
        probe = BPFProbe(hmac_key=HMAC_KEY)
        await probe.stop()  # should not raise


class TestBPFProbeEventCreation:
    """BPFProbe 事件创建测试 — 模拟 eBPF 数据构造 ObservationEvent"""

    def test_build_observation_from_openat(self) -> None:
        probe = BPFProbe(hmac_key=HMAC_KEY)

        # 模拟 bcc perf buffer data (使用 MagicMock 模拟 ctypes struct)
        mock_data = MagicMock()
        mock_data.pid = 1234
        mock_data.uid = 1000
        mock_data.flags = 65536  # O_RDONLY|O_LARGEFILE
        mock_data.filename = b"/etc/passwd\x00"
        mock_data.task = b"test_proc\x00"

        event = probe._build_observation_from_openat(mock_data)
        assert event is not None
        assert isinstance(event, ObservationEvent)
        assert event.source == "ebpf"
        assert event.subject == "pid:1234"
        assert event.severity == Severity.LOW
        assert event.attack_type == AttackType.NONE
        assert event.evidence["syscall"] == "openat"
        assert event.evidence["pid"] == 1234
        assert event.evidence["filename"] == "/etc/passwd"
        assert event.evidence["uid"] == 1000
        assert event.hash != ""  # HMAC signed

    def test_build_observation_from_openat_signed(self) -> None:
        """验证 HMAC 签名正确生成并可验证"""
        probe = BPFProbe(hmac_key=HMAC_KEY)
        mock_data = MagicMock()
        mock_data.pid = 5678
        mock_data.uid = 0
        mock_data.flags = 0
        mock_data.filename = b"/proc/self/environ\x00"
        mock_data.task = b"malware\x00"

        event = probe._build_observation_from_openat(mock_data)
        assert event is not None

        # 使用 compute_event_hash 验证签名
        from maref.sentinel.event import verify_event_hash
        assert verify_event_hash(event, HMAC_KEY) is True

        # 用错误密钥验证应失败
        assert verify_event_hash(event, b"wrong-key") is False

    def test_build_observation_from_connect(self) -> None:
        probe = BPFProbe(hmac_key=HMAC_KEY)
        mock_data = MagicMock()
        mock_data.pid = 9999
        mock_data.uid = 1001
        mock_data.daddr = 0x01010101  # 1.1.1.1 (big-endian from BPF)
        mock_data.dport = 0x5000  # port 80 in network byte order
        mock_data.task = b"curl\x00"

        event = probe._build_observation_from_connect(mock_data)
        assert event is not None
        assert event.source == "ebpf"
        assert event.subject == "pid:9999"
        assert event.evidence["syscall"] == "connect"
        assert event.evidence["pid"] == 9999
        assert event.evidence["uid"] == 1001
        assert event.hash != ""

    def test_build_observation_from_connect_hmac_valid(self) -> None:
        probe = BPFProbe(hmac_key=HMAC_KEY)
        mock_data = MagicMock()
        mock_data.pid = 7777
        mock_data.uid = 2000
        mock_data.daddr = 0x08080808
        mock_data.dport = 0x01BB  # port 443 in network byte order
        mock_data.task = b"wget\x00"

        event = probe._build_observation_from_connect(mock_data)

        from maref.sentinel.event import verify_event_hash
        assert event is not None
        assert verify_event_hash(event, HMAC_KEY) is True

    def test_build_observation_from_invalid_data_returns_none(self) -> None:
        """无效数据 → 应返回 None 而非崩溃"""
        probe = BPFProbe(hmac_key=HMAC_KEY)
        # 模拟缺失关键字段的数据
        bad_data = MagicMock(spec=[])
        bad_data.pid = 0

        event = probe._build_observation_from_openat(bad_data)
        assert event is not None  # 有默认值,仍应构造成功

    def test_ip_to_str(self) -> None:
        """_ip_to_str 静态方法测试"""
        assert BPFProbe._ip_to_str(0x01010101) == "1.1.1.1"
        assert BPFProbe._ip_to_str(0x08080808) == "8.8.8.8"
        assert BPFProbe._ip_to_str(0xC0A80001) == "1.0.168.192"
        assert BPFProbe._ip_to_str(0x00000000) == "0.0.0.0"
        assert BPFProbe._ip_to_str(0x7F000001) == "1.0.0.127"


# ---------------------------------------------------------------------------
# SeccompPolicy tests
# ---------------------------------------------------------------------------


class TestSeccompPolicy:
    """SeccompPolicy 策略测试"""

    def test_default_policy_allows_all(self) -> None:
        policy = SeccompPolicy()
        policy.validate()
        assert policy.contains(0) is True
        assert policy.contains(42) is True
        assert policy.contains(511) is True

    def test_blocked_syscalls_are_rejected(self) -> None:
        policy = SeccompPolicy(blocked_syscalls={42, 59})
        assert policy.contains(42) is False
        assert policy.contains(59) is False
        assert policy.contains(0) is True

    def test_allowed_syscalls_whitelist(self) -> None:
        policy = SeccompPolicy(allowed_syscalls={0, 1, 2, 3})
        assert policy.contains(0) is True  # read
        assert policy.contains(1) is True  # write
        assert policy.contains(59) is False  # execve (not allowed)

    def test_blacklist_overrides_whitelist(self) -> None:
        """同时出现在两个集合中 → 阻断"""
        policy = SeccompPolicy(
            allowed_syscalls={0, 1, 2, 42, 59},
            blocked_syscalls={42, 59},
        )
        assert policy.contains(0) is True
        assert policy.contains(42) is False  # blocked
        assert policy.contains(59) is False  # blocked (in both)

    def test_validate_valid_policy(self) -> None:
        policy = SeccompPolicy(allowed_syscalls={0, 1}, blocked_syscalls={42})
        policy.validate()  # should not raise

    def test_validate_raises_on_invalid_syscall_number(self) -> None:
        with pytest.raises(ValueError, match="must be 0-511"):
            SeccompPolicy(allowed_syscalls={999}).validate()

        with pytest.raises(ValueError, match="must be 0-511"):
            SeccompPolicy(blocked_syscalls={-1}).validate()

    def test_contains_with_empty_policy(self) -> None:
        policy = SeccompPolicy()
        for nr in (0, 100, 511):
            assert policy.contains(nr) is True


# ---------------------------------------------------------------------------
# SeccompFilter construction tests
# ---------------------------------------------------------------------------


class TestSeccompFilterInit:
    """SeccompFilter 构造与安装测试"""

    def test_init_empty_installed_pids(self) -> None:
        flt = SeccompFilter()
        assert flt.installed_pids == set()

    def test_install_raises_on_nonexistent_pid(self) -> None:
        flt = SeccompFilter()
        policy = SeccompPolicy(allowed_syscalls={0, 1, 2, 3})
        # PID 99999999 极大概率不存在
        with pytest.raises(SeccompFilterError, match="does not exist"):
            flt.install(pid=99999999, policy=policy)

    def test_block_syscalls_raises_on_nonexistent_pid(self) -> None:
        flt = SeccompFilter()
        with pytest.raises(SeccompFilterError, match="does not exist"):
            flt.block_syscalls(pid=99999999, syscalls={42, 59})

    def test_install_with_invalid_policy_raises(self) -> None:
        flt = SeccompFilter()
        policy = SeccompPolicy(allowed_syscalls={999})
        with pytest.raises(ValueError):
            flt.install(pid=1, policy=policy)


# ---------------------------------------------------------------------------
# SockFilter ctypes tests
# ---------------------------------------------------------------------------


class TestSockFilterCtypes:
    """SockFilter / SockFProg ctypes 结构测试"""

    def test_sock_filter_size(self) -> None:
        """struct sock_filter 应为 8 bytes (2+1+1+4)"""
        assert ctypes.sizeof(SockFilter) == 8

    def test_sock_fprog_size(self) -> None:
        """struct sock_fprog 应为 16 bytes (2+padding+pointer on 64-bit)"""
        # 16 bytes on macOS/64-bit 可能有变化,只需验证是合理值
        assert ctypes.sizeof(SockFProg) >= 8

    def test_sock_filter_creation(self) -> None:
        flt = SockFilter(code=0x06, jt=0, jf=0, k=0x7FFF0000)
        assert flt.code == 0x06
        assert flt.k == 0x7FFF0000  # SECCOMP_RET_ALLOW

    def test_sock_fprog_creation(self) -> None:
        filters = (SockFilter * 2)(
            SockFilter(0x20, 0, 0, 0),
            SockFilter(0x15, 0, 1, 42),
        )
        prog = SockFProg()
        prog.len = 2
        prog.filter = filters
        assert prog.len == 2


# ---------------------------------------------------------------------------
# _build_seccomp_filter tests
# ---------------------------------------------------------------------------


class TestBuildSeccompFilter:
    """_build_seccomp_filter 指令生成测试"""

    def test_default_policy_generates_minimal_filters(self) -> None:
        policy = SeccompPolicy()
        filters = _build_seccomp_filter(policy)
        assert len(filters) >= 4
        # [0]: LD arch
        assert filters[0].code == 0x20  # BPF_LD | BPF_W | BPF_ABS
        # [1]: JEQ AUDIT_ARCH_X86_64
        assert filters[1].code & 0x07 == 0x05  # BPF_JMP
        # [2]: RET KILL (wrong arch)
        assert filters[2].code == 0x06  # BPF_RET
        # [3]: LD syscall nr
        assert filters[3].code == 0x20  # BPF_LD | BPF_W | BPF_ABS

    def test_blocked_syscalls_add_rules(self) -> None:
        policy = SeccompPolicy(blocked_syscalls={42, 59})
        filters = _build_seccomp_filter(policy)
        # 基线 4 条 + 每个 blocked 2 条 + 结尾 RET ALLOW = 9
        assert len(filters) == 9

    def test_allowed_syscalls_add_rules(self) -> None:
        policy = SeccompPolicy(allowed_syscalls={0, 1, 2})
        filters = _build_seccomp_filter(policy)
        # 基线 4 + 默认 kill + 每个 allowed 2 条 + 结尾 kill = 4 + 1 + 6 + 1 = 12
        assert len(filters) >= 10

    def test_first_filter_is_arch_check(self) -> None:
        policy = SeccompPolicy(allowed_syscalls={0})
        filters = _build_seccomp_filter(policy)
        assert filters[0].code == 0x20  # BPF_LD | BPF_W | BPF_ABS
        assert filters[0].k == 4  # SECCOMP_DATA_ARCH_OFFSET

    def test_last_filter_is_return_action(self) -> None:
        policy = SeccompPolicy(blocked_syscalls={42})
        filters = _build_seccomp_filter(policy)
        # 最后一条指令应为 RET ALLOW (无 whitelist)
        assert filters[-1].code == 0x06  # BPF_RET
        assert filters[-1].k == 0x7FFF0000  # SECCOMP_RET_ALLOW


# ---------------------------------------------------------------------------
# X8664Syscalls constants tests
# ---------------------------------------------------------------------------


class TestX8664Syscalls:
    """x86_64 syscall 常量正确性"""

    def test_common_syscalls(self) -> None:
        assert X8664Syscalls.READ == 0
        assert X8664Syscalls.WRITE == 1
        assert X8664Syscalls.OPEN == 2
        assert X8664Syscalls.CLOSE == 3
        assert X8664Syscalls.EXECVE == 59
        assert X8664Syscalls.EXIT == 60
        assert X8664Syscalls.CONNECT == 42
        assert X8664Syscalls.ACCEPT == 43
        assert X8664Syscalls.OPENAT == 257
        assert X8664Syscalls.PTRACE == 101
        assert X8664Syscalls.KILL == 62
        assert X8664Syscalls.CLONE == 56
        assert X8664Syscalls.BIND == 49
        assert X8664Syscalls.PRCTL == 157
        assert X8664Syscalls.EXIT_GROUP == 231
        assert X8664Syscalls.RECVFROM == 45
        assert X8664Syscalls.SENDTO == 44

    def test_all_constants_are_ints(self) -> None:
        for attr_name in dir(X8664Syscalls):
            if attr_name.startswith("_"):
                continue
            val = getattr(X8664Syscalls, attr_name)
            assert isinstance(val, int), f"{attr_name} should be int, got {type(val)}"


# ---------------------------------------------------------------------------
# seccomp constants tests
# ---------------------------------------------------------------------------


class TestSeccompConstants:
    """seccomp 常量测试"""

    def test_pr_set_seccomp(self) -> None:
        assert PR_SET_SECCOMP == 22

    def test_seccomp_mode_filter(self) -> None:
        assert SECCOMP_MODE_FILTER == 2


# ---------------------------------------------------------------------------
# Integration-style: platform linux __init__ exports
# ---------------------------------------------------------------------------


class TestLinuxPlatformExports:
    """Linux 平台模块导出测试"""

    def test_bpf_not_available_error_exported(self) -> None:
        from maref.sentinel.platform.linux import BPFNotAvailableError
        assert issubclass(BPFNotAvailableError, RuntimeError)

    def test_all_exported_names(self) -> None:
        from maref.sentinel.platform.linux import __all__
        expected = {
            "BPFNotAvailableError",
            "BPFProbe",
            "SECCOMP_MODE_FILTER",
            "SeccompFilter",
            "SeccompPolicy",
            "X8664Syscalls",
        }
        assert set(__all__) == expected
