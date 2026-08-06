"""
seccomp_filter — Linux seccomp-bpf 进程级 syscall 过滤

通过 ctypes 调用 prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, prog)
安装 seccomp BPF 过滤器,限制目标进程的 syscall 权限。

与 BPFProbe 形成互补:
- BPFProbe: 被动观测,不干预进程行为
- SeccompFilter: 主动阻断,限制白名单之外的 syscall

参考架构: seccomp-bpf 规则链 (cBPF) 在 prctl 内核路径生效,
PID 为 -1 时作用于当前进程。
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# x86_64 syscall number constants
# ---------------------------------------------------------------------------


class X8664Syscalls:
    """x86_64 架构 syscall 号常量

    仅包含 sentinel 关注的核心 syscall。完整列表见 /usr/include/x86_64-linux-gnu/asm/unistd_64.h
    """

    READ: int = 0
    WRITE: int = 1
    OPEN: int = 2
    CLOSE: int = 3
    STAT: int = 4
    FSTAT: int = 5
    LSTAT: int = 6
    POLL: int = 7
    LSEEK: int = 8
    MMAP: int = 9
    MPROTECT: int = 10
    MUNMAP: int = 11
    BRK: int = 12
    RT_SIGACTION: int = 13
    RT_SIGPROCMASK: int = 14
    RT_SIGRETURN: int = 15
    IOCTL: int = 16
    PREAD64: int = 17
    PWRITE64: int = 18
    READV: int = 19
    WRITEV: int = 20
    ACCESS: int = 21
    PIPE: int = 22
    SELECT: int = 23
    SCHED_YIELD: int = 24
    MREMAP: int = 25
    MSYNC: int = 26
    MINCORE: int = 27
    MADVISE: int = 28
    SHMGET: int = 29
    SHMAT: int = 30
    SHMCTL: int = 31
    DUP: int = 32
    DUP2: int = 33
    PAUSE: int = 34
    NANOSLEEP: int = 35
    GETITIMER: int = 36
    ALARM: int = 37
    SETITIMER: int = 38
    GETPID: int = 39
    SENDFILE: int = 40
    SOCKET: int = 41
    CONNECT: int = 42
    ACCEPT: int = 43
    SENDTO: int = 44
    RECVFROM: int = 45
    SENDMSG: int = 46
    RECVMSG: int = 47
    SHUTDOWN: int = 48
    BIND: int = 49
    LISTEN: int = 50
    GETSOCKNAME: int = 51
    GETPEERNAME: int = 52
    SOCKETPAIR: int = 53
    SETSOCKOPT: int = 54
    GETSOCKOPT: int = 55
    CLONE: int = 56
    FORK: int = 57
    VFORK: int = 58
    EXECVE: int = 59
    EXIT: int = 60
    WAIT4: int = 61
    KILL: int = 62
    UNAME: int = 63
    SEMGET: int = 64
    SEMOP: int = 65
    SEMCTL: int = 66
    SHMDT: int = 67
    MSGGET: int = 68
    MSGSND: int = 69
    MSGRCV: int = 70
    MSGCTL: int = 71
    FCNTL: int = 72
    FLOCK: int = 73
    FSYNC: int = 74
    FDATASYNC: int = 75
    TRUNCATE: int = 76
    FTRUNCATE: int = 77
    GETDENTS: int = 78
    GETCWD: int = 79
    CHDIR: int = 80
    FCHDIR: int = 81
    RENAME: int = 82
    MKDIR: int = 83
    RMDIR: int = 84
    CREAT: int = 85
    LINK: int = 86
    UNLINK: int = 87
    SYMLINK: int = 88
    READLINK: int = 89
    CHMOD: int = 90
    FCHMOD: int = 91
    CHOWN: int = 92
    FCHOWN: int = 93
    LCHOWN: int = 94
    UMASK: int = 95
    GETTIMEOFDAY: int = 96
    GETRLIMIT: int = 97
    GETRUSAGE: int = 98
    SYSINFO: int = 99
    TIMES: int = 100
    PTRACE: int = 101
    GETUID: int = 102
    SYSLOG: int = 103
    GETGID: int = 104
    SETUID: int = 105
    SETGID: int = 106
    GETEUID: int = 107
    GETEGID: int = 108
    SETPGID: int = 109
    GETPPID: int = 110
    GETPGRP: int = 111
    SETSID: int = 112
    SETREUID: int = 113
    SETREGID: int = 114
    GETGROUPS: int = 115
    SETGROUPS: int = 116
    SETRESUID: int = 117
    GETRESUID: int = 118
    SETRESGID: int = 119
    GETRESGID: int = 120
    GETPGID: int = 121
    SETFSUID: int = 122
    SETFSGID: int = 123
    GETSID: int = 124
    CAPGET: int = 125
    CAPSET: int = 126
    RT_SIGPENDING: int = 127
    RT_SIGTIMEDWAIT: int = 128
    RT_SIGQUEUEINFO: int = 129
    RT_SIGSUSPEND: int = 130
    SIGALTSTACK: int = 131
    UTIME: int = 132
    MKNOD: int = 133
    USELIB: int = 134
    PERSONALITY: int = 135
    USTAT: int = 136
    STATFS: int = 137
    FSTATFS: int = 138
    SYSFS: int = 139
    GETPRIORITY: int = 140
    SETPRIORITY: int = 141
    SCHED_SETPARAM: int = 142
    SCHED_GETPARAM: int = 143
    SCHED_SETSCHEDULER: int = 144
    SCHED_GETSCHEDULER: int = 145
    SCHED_GET_PRIORITY_MAX: int = 146
    SCHED_GET_PRIORITY_MIN: int = 147
    SCHED_RR_GET_INTERVAL: int = 148
    MLOCK: int = 149
    MUNLOCK: int = 150
    MLOCKALL: int = 151
    MUNLOCKALL: int = 152
    VHANGUP: int = 153
    MODIFY_LDT: int = 154
    PIVOT_ROOT: int = 155
    _SYSCTL: int = 156
    PRCTL: int = 157
    ARCH_PRCTL: int = 158
    ADJTIMEX: int = 159
    SETRLIMIT: int = 160
    CHROOT: int = 161
    SYNC: int = 162
    ACCT: int = 163
    SETTIMEOFDAY: int = 164
    MOUNT: int = 165
    UMOUNT2: int = 166
    SWAPON: int = 167
    SWAPOFF: int = 168
    REBOOT: int = 169
    SETHOSTNAME: int = 170
    SETDOMAINNAME: int = 171
    IOPL: int = 172
    IOPERM: int = 173
    CREATE_MODULE: int = 174
    INIT_MODULE: int = 175
    DELETE_MODULE: int = 176
    GET_KERNEL_SYMS: int = 177
    QUERY_MODULE: int = 178
    QUOTACTL: int = 179
    NFSSERVCTL: int = 180
    GETPMSG: int = 181
    PUTPMSG: int = 182
    AFS_SYSCALL: int = 183
    TUXCALL: int = 184
    SECURITY: int = 185
    GETTID: int = 186
    READAHEAD: int = 187
    SETXATTR: int = 188
    LSETXATTR: int = 189
    FSETXATTR: int = 190
    GETXATTR: int = 191
    LGETXATTR: int = 192
    FGETXATTR: int = 193
    LISTXATTR: int = 194
    LLISTXATTR: int = 195
    FLISTXATTR: int = 196
    REMOVEXATTR: int = 197
    LREMOVEXATTR: int = 198
    FREMOVEXATTR: int = 199
    TKDONLY: int = 200
    IO_SETUP: int = 201
    IO_DESTROY: int = 202
    IO_GETEVENTS: int = 203
    IO_SUBMIT: int = 204
    IO_CANCEL: int = 205
    EXIT_GROUP: int = 231
    MPROTECT_STRICT: int = 232
    SET_TID_ADDRESS: int = 233
    OPENAT: int = 257
    MKDIRAT: int = 258
    MKNODAT: int = 259
    FCHOWNAT: int = 260
    FUTIMESAT: int = 261
    NEWFSTATAT: int = 262
    UNLINKAT: int = 263
    RENAMEAT: int = 264
    LINKAT: int = 265
    SYMLINKAT: int = 266
    READLINKAT: int = 267
    FCHMODAT: int = 268
    FACESSAT: int = 269
    PSELECT6: int = 270
    PPOL: int = 271
    UNSHARE: int = 272
    SET_ROBUST_LIST: int = 273
    GET_ROBUST_LIST: int = 274
    SPLICE: int = 275
    TEE: int = 276
    SYNC_FILE_RANGE: int = 277
    VMSPLICE: int = 278
    MOVE_PAGES: int = 279
    UTIMENSAT: int = 280
    EPRO_POLL: int = 281
    EPRO_POLL_CTL: int = 282
    EPRO_POLL_WAIT: int = 283
    TIMERFD_CREATE: int = 284
    TIMERFD_SETTIME: int = 285
    TIMERFD_GETTIME: int = 286
    EVENTFD: int = 287
    DGRAM_SOCKET: int = 288
    INOTIFY_INIT: int = 291
    INOTIFY_ADD_WATCH: int = 292
    INOTIFY_RM_WATCH: int = 293
    SIGNALFD: int = 294
    OLD_SIGSUSPEND: int = 295
    RECVMMSG: int = 299


# ---------------------------------------------------------------------------
# seccomp constants (from linux/seccomp.h)
# ---------------------------------------------------------------------------

PR_SET_SECCOMP: int = 22
"""prctl 操作码: 设置 seccomp 过滤器"""

SECCOMP_MODE_FILTER: int = 2
"""seccomp 模式: BPF 过滤器模式"""

SECCOMP_RET_KILL: int = 0x00000000
"""seccomp 返回值: 杀死进程"""

SECCOMP_RET_TRAP: int = 0x00030000
"""seccomp 返回值: 触发 SIGSYS"""

SECCOMP_RET_ERRNO: int = 0x00050000
"""seccomp 返回值: 返回 EPERM/ENOSYS"""

SECCOMP_RET_TRACE: int = 0x7FF00000
"""seccomp 返回值: 通知 tracer"""

SECCOMP_RET_ALLOW: int = 0x7FFF0000
"""seccomp 返回值: 放行"""

# ---------------------------------------------------------------------------
# sock_fprog / sock_filter ctypes structures
# ---------------------------------------------------------------------------


class SockFilter(ctypes.Structure):
    """struct sock_filter — BPF 指令"""

    _fields_: list[tuple[str, Any]] = [  # type: ignore[misc]
        ("code", ctypes.c_uint16),
        ("jt", ctypes.c_uint8),
        ("jf", ctypes.c_uint8),
        ("k", ctypes.c_uint32),
    ]


class SockFProg(ctypes.Structure):
    """struct sock_fprog — BPF 程序"""

    _fields_: list[tuple[str, Any]] = [  # type: ignore[misc]
        ("len", ctypes.c_ushort),  # filter 数量
        ("filter", ctypes.POINTER(SockFilter)),  # filter 数组指针
    ]


# ---------------------------------------------------------------------------
# SeccompPolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeccompPolicy:
    """seccomp 过滤策略

    allowed_syscalls: 白名单 syscall 集合 (空 = 不允许任何 syscall)
    blocked_syscalls: 黑名单 syscall 集合 (优先级高于白名单)

    当白名单非空时,仅白名单内的 syscall 被放行,其余被阻断。
    当白名单为空时,黑名单内的 syscall 被阻断,其余放行。

    黑名单优先级高于白名单: 同时出现在两个集合中的 syscall 被阻断。
    """

    allowed_syscalls: set[int] = field(default_factory=set)
    blocked_syscalls: set[int] = field(default_factory=set)

    def validate(self) -> None:
        """校验策略 — 确保 syscall 号在合法范围内

        Raises:
            ValueError: syscall 号超出 [0, 511] 范围
        """
        for nr in self.allowed_syscalls:
            if not (0 <= nr <= 511):
                raise ValueError(f"invalid syscall number: {nr} (must be 0-511)")
        for nr in self.blocked_syscalls:
            if not (0 <= nr <= 511):
                raise ValueError(f"invalid syscall number: {nr} (must be 0-511)")

    def contains(self, syscall_nr: int) -> bool:
        """检查某 syscall 是否被策略允许

        Args:
            syscall_nr: 目标 syscall 号

        Returns:
            True = 放行, False = 阻断
        """
        if syscall_nr in self.blocked_syscalls:
            return False
        if self.allowed_syscalls:
            return syscall_nr in self.allowed_syscalls
        return True


# ---------------------------------------------------------------------------
# BPF instruction helpers
# ---------------------------------------------------------------------------


def _bpf_stmt(code: int, k: int) -> SockFilter:
    """创建 BPF 语句指令 (无跳转)"""
    return SockFilter(code, 0, 0, k)


def _bpf_jump(code: int, k: int, jt: int, jf: int) -> SockFilter:
    """创建 BPF 跳转指令"""
    return SockFilter(code, jt, jf, k)


# BPF instruction codes (linux/bpf_common.h)
BPF_LD: int = 0x00
BPF_LDX: int = 0x01
BPF_ST: int = 0x02
BPF_STX: int = 0x03
BPF_ALU: int = 0x04
BPF_JMP: int = 0x05
BPF_RET: int = 0x06
BPF_MISC: int = 0x07

BPF_W: int = 0x00  # 32-bit word
BPF_H: int = 0x08  # 16-bit half-word
BPF_B: int = 0x10  # 8-bit byte

BPF_ABS: int = 0x20  # 绝对寻址

BPF_JEQ: int = 0x10  # jump if ==
BPF_JGT: int = 0x20  # jump if >
BPF_JGE: int = 0x30  # jump if >=
BPF_JSET: int = 0x40  # jump if & != 0

BPF_K: int = 0x00  # 使用常量 k

# seccomp data offsets (arch/x86/include/asm/seccomp.h)
SECCOMP_DATA_NR_OFFSET: int = 0  # syscall number offset
SECCOMP_DATA_ARCH_OFFSET: int = 4  # architecture offset

# AUDIT_ARCH_X86_64
AUDIT_ARCH_X86_64: int = 0xC000003E


def _build_seccomp_filter(
    policy: SeccompPolicy,
    kill_action: int = SECCOMP_RET_KILL,
    allow_action: int = SECCOMP_RET_ALLOW,
) -> list[SockFilter]:
    """构建 seccomp BPF 过滤器指令列表

    生成经典 BPF (cBPF) 指令序列:

    1. 检查架构是否为 x86_64 (拒绝非原生 32-bit 兼容调用)
    2. 加载 syscall number
    3. 遍历策略规则 (blacklist/whitelist)
    4. 返回 kill/allow

    Args:
        policy: seccomp 过滤策略
        kill_action: 阻断时返回的 seccomp 动作 (默认 KILL)
        allow_action: 放行时返回的 seccomp 动作 (默认 ALLOW)

    Returns:
        SockFilter 指令列表 (cBPF)
    """
    filters: list[SockFilter] = []

    # Load architecture (data[4])
    filters.append(_bpf_stmt(BPF_LD | BPF_W | BPF_ABS, SECCOMP_DATA_ARCH_OFFSET))
    # Jump if == AUDIT_ARCH_X86_64, else kill
    filters.append(_bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0))
    filters.append(_bpf_stmt(BPF_RET | BPF_K, kill_action))

    # Load syscall number (data[0])
    filters.append(_bpf_stmt(BPF_LD | BPF_W | BPF_ABS, SECCOMP_DATA_NR_OFFSET))

    # Generate blacklist rules
    if policy.blocked_syscalls:
        for nr in sorted(policy.blocked_syscalls):
            filters.append(_bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, nr, 0, 1))
            filters.append(_bpf_stmt(BPF_RET | BPF_K, kill_action))

    # Generate whitelist rules
    if policy.allowed_syscalls:
        allowed = sorted(policy.allowed_syscalls - policy.blocked_syscalls)
        # Default: kill
        filters.append(_bpf_stmt(BPF_RET | BPF_K, kill_action))
        for nr in allowed:
            filters.append(_bpf_jump(BPF_JMP | BPF_JEQ | BPF_K, nr, 0, 1))
            filters.append(_bpf_stmt(BPF_RET | BPF_K, allow_action))
        filters.append(_bpf_stmt(BPF_RET | BPF_K, kill_action))
    else:
        filters.append(_bpf_stmt(BPF_RET | BPF_K, allow_action))

    return filters


# ---------------------------------------------------------------------------
# SeccompFilter
# ---------------------------------------------------------------------------


class SeccompFilterError(RuntimeError):
    """seccomp 过滤器安装错误"""


class SeccompFilter:
    """Linux seccomp-bpf 进程级 syscall 过滤器

    通过 ctypes 调用 prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, prog)
    安装经典 BPF (cBPF) 指令序列,限制指定进程的 syscall 权限。

    Usage:
        policy = SeccompPolicy(
            allowed_syscalls={X8664Syscalls.READ, X8664Syscalls.WRITE, X8664Syscalls.CLOSE},
        )
        filt = SeccompFilter()
        success = filt.install(pid=1234, policy=policy)
    """

    def __init__(self) -> None:
        self._libc: Any = None
        self._installed_pids: set[int] = set()

    @property
    def installed_pids(self) -> set[int]:
        """返回已安装过滤器的 PID 集合"""
        return self._installed_pids.copy()

    def install(self, pid: int, policy: SeccompPolicy) -> bool:
        """为目标进程安装 seccomp BPF 过滤器

        通过 prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, prog) 实现。
        过滤器以 cBPF 指令序列形式传入内核。

        Args:
            pid: 目标进程 PID。若为 -1 或 0,作用于当前进程 (Python 进程自身)。
            policy: seccomp 过滤策略

        Returns:
            True = 安装成功

        Raises:
            SeccompFilterError: prctl 调用失败或目标进程不存在
            ValueError: 策略无效或 pid 不合法
        """
        policy.validate()

        effective_pid = os.getpid() if pid <= 0 else pid

        # 验证目标进程存在
        if pid > 0:
            try:
                os.kill(effective_pid, 0)
            except OSError:
                raise SeccompFilterError(f"target pid {effective_pid} does not exist") from None

        self._ensure_libc()

        # 构建 BPF 指令
        filters = _build_seccomp_filter(policy)
        filter_array = (SockFilter * len(filters))(*filters)

        prog = SockFProg()
        prog.len = ctypes.c_ushort(len(filters))
        prog.filter = filter_array

        # 如果目标不是当前进程,需要先 attach (ptrace)
        # 对当前进程,直接调用 prctl
        if effective_pid == os.getpid() or pid <= 0:
            result = self._libc.prctl(
                PR_SET_SECCOMP,
                SECCOMP_MODE_FILTER,
                ctypes.byref(prog),
            )
            if result != 0:
                errno_val = ctypes.get_errno()
                raise SeccompFilterError(
                    f"prctl(PR_SET_SECCOMP) failed for pid {effective_pid}: "
                    f"errno={errno_val}"
                )
        else:
            # 对其他进程: 需要先 attach 再执行 prctl
            # 使用 process_vm_writev 注入 seccomp 过滤器
            raise SeccompFilterError(
                f"cannot install seccomp filter on remote pid {effective_pid}: "
                "remote process filtering requires SECCOMP_IOCTL_NOTIF_RECV on Linux >= 5.0"
            )

        self._installed_pids.add(effective_pid)
        return True

    def block_syscalls(self, pid: int, syscalls: set[int]) -> bool:
        """快速阻断指定 syscall 集合

        构造仅包含阻断规则的 SeccompPolicy 并安装。
        白名单为空 = 仅阻断指定 syscall,其余放行。

        Args:
            pid: 目标进程 PID
            syscalls: 要阻断的 syscall 号集合

        Returns:
            True = 安装成功
        """
        policy = SeccompPolicy(blocked_syscalls=syscalls)
        return self.install(pid, policy)

    def _ensure_libc(self) -> None:
        """确保 libc 已加载 (ctypes.CDLL)"""
        if self._libc is not None:
            return

        libc_path = ctypes.util.find_library("c")
        if libc_path is None:
            raise SeccompFilterError("libc not found — cannot call prctl")
        self._libc = ctypes.CDLL(libc_path, use_errno=True)

        # prctl signature: int prctl(int option, unsigned long arg2, unsigned long arg3, ...)
        self._libc.prctl.argtypes = [
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        self._libc.prctl.restype = ctypes.c_int
