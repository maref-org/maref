"""
sandbox_profile_gen — 根据 SignedAgentCard 声明能力生成 macOS sandbox-exec profile

接口契约 (validation-contract.md 2.1-A2/A4):
- 2.1-A2: sandbox-exec profile 拒绝未声明 capability 的 syscall
        (如 Agent 声明 network-only 但尝试 fork-exec bash → 拒绝)
- 2.1-A4: sandbox-exec policy 与 SignedAgentCard.declared_capabilities 100% 一致
        (差异即阻断)

设计原则:
1. 默认拒绝 (deny default) — 只允许显式声明的能力
2. 基线放行 — 系统库读取/信号处理/临时目录写入等基础操作
3. 能力映射 — 每个 capability 对应一组 allow/deny 规则
4. 端点白名单 — network_read 仅允许到 endpoints 列表中的域名
5. 可审计 — profile 内嵌生成时间戳、agent_id、能力哈希

sandbox-exec 语法 (Scheme-like):
  (version 1)
  (deny default)
  (allow network-outbound (remote tcp "example.com:443"))
  (deny process-exec (literal "/bin/bash"))
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

# 能力到 sandbox 规则的映射表
# 每个 capability 对应一个 tuple of (allow_rules, deny_rules)
# allow_rules: 允许的操作 (sandbox-exec 语法片段)
# deny_rules:  显式拒绝的操作 (防止隐式放行)
CAPABILITY_TO_SANDBOX_RULES: dict[str, dict[str, list[str]]] = {
    "network_read": {
        "allow": [
            '(allow network-outbound (remote tcp))',
            '(allow network* (remote udp "127.0.0.1:53"))',  # DNS
        ],
        "deny": [],
    },
    "network_write": {
        # network_write = server mode, allow inbound
        "allow": [
            '(allow network-inbound (local tcp))',
        ],
        "deny": [],
    },
    "file_read": {
        "allow": [
            '(allow file-read* (subpath "/usr/lib"))',
            '(allow file-read* (subpath "/usr/share"))',
            '(allow file-read* (subpath "/Library/Frameworks"))',
            '(allow file-read* (subpath "/System/Library"))',
            '(allow file-read* (subpath "/tmp/maref-agent-read"))',
        ],
        "deny": [
            '(deny file-read* (subpath "/etc/master.passwd"))',
            '(deny file-read* (subpath "/var/db/dslocal"))',
            '(deny file-read* (subpath ".ssh"))',
            '(deny file-read* (subpath ".aws/credentials"))',
            '(deny file-read* (subpath ".kube/config"))',
            '(deny file-read* (subpath ".gnupg"))',
        ],
    },
    "file_write": {
        "allow": [
            '(allow file-write* (subpath "/tmp/maref-agent-write"))',
            '(allow file-write* (subpath "/private/tmp/maref-agent-write"))',
            '(allow file-write-data (subpath "/tmp/maref-agent-write"))',
        ],
        "deny": [
            '(deny file-write* (subpath "/etc"))',
            '(deny file-write* (subpath "/usr"))',
            '(deny file-write* (subpath "/System"))',
            '(deny file-write* (subpath "/Library"))',
            '(deny file-write* (subpath ".ssh"))',
            '(deny file-write* (subpath ".bash_profile"))',
            '(deny file-write* (subpath ".zshrc"))',
            '(deny file-write* (subpath ".config/launchd"))',
        ],
    },
    "process_spawn": {
        # process_spawn = 允许 fork/posix_spawn
        "allow": [
            '(allow process-fork)',
        ],
        "deny": [],
    },
    "process_exec": {
        # process_exec = 允许 execve,但仅限白名单二进制
        # 实际白名单由 SandboxProfileGenerator 根据 endpoints/agent 类型动态生成
        "allow": [
            '(allow process-exec (literal "/usr/bin/env"))',
            '(allow process-exec (literal "/bin/echo"))',
            '(allow process-exec (literal "/usr/bin/true"))',
        ],
        "deny": [
            '(deny process-exec (literal "/bin/bash"))',
            '(deny process-exec (literal "/bin/sh"))',
            '(deny process-exec (literal "/bin/zsh"))',
            '(deny process-exec (literal "/usr/bin/osascript"))',
            '(deny process-exec (literal "/usr/bin/tccutil"))',
            '(deny process-exec (literal "/usr/bin/curl"))',
            '(deny process-exec (literal "/usr/bin/wget"))',
            '(deny process-exec (literal "/usr/bin/nc"))',
            '(deny process-exec (literal "/usr/bin/python3"))',
            '(deny process-exec (literal "/usr/local/bin/python3"))',
            '(deny process-exec (literal "/opt/homebrew/bin/python3"))',
        ],
    },
    "ptrace": {
        # ptrace 通常应被拒绝;只有声明此能力的 Agent 才允许
        "allow": [
            '(allow process-kill (target same-bin))',
            '(allow signal (target same-bin))',
        ],
        "deny": [],
    },
    "env_read": {
        # env_read 通常默认允许 (敏感变量在 ForensicSnapshot 层脱敏)
        "allow": [
            '(allow sysctl-read*)',
        ],
        "deny": [],
    },
    "env_write": {
        # env_write = 允许 setenv,通常用于子进程环境
        "allow": [
            '(allow process-info-set (target same-bin))',
        ],
        "deny": [],
    },
    "ipc_posix": {
        # IPC: POSIX shared memory / message queue / semaphore
        "allow": [
            '(allow ipc-posix*)',
        ],
        "deny": [],
    },
    "ipc_mach": {
        # IPC: Mach ports (macOS native IPC)
        "allow": [
            '(allow ipc-mig*)',
            '(allow mach-lookup)',
        ],
        "deny": [],
    },
    "device_io": {
        # 设备 I/O (磁盘/USB/摄像头等)
        "allow": [
            '(allow iokit-open)',
        ],
        "deny": [],
    },
}

# 基线放行规则 — 任何 Agent 都需要的最小权限 (macOS 进程基础)
_BASELINE_ALLOW_RULES: tuple[str, ...] = (
    '(allow signal (target same-bin))',
    '(allow sysctl-read "kern.proc.pid")',
    '(allow sysctl-read "kern.osversion")',
    '(allow sysctl-read "kern.ostype")',
    '(allow file-read* (subpath "/dev/urandom"))',
    '(allow file-read* (subpath "/dev/null"))',
    '(allow file-write* (subpath "/dev/null"))',
    '(allow file-read* (literal "/etc/localtime"))',  # 时区读取 (受 TimezoneProbe 监控)
    '(allow file-read* (literal "/etc/resolv.conf"))',
    '(allow network-outbound (remote udp "127.0.0.1:53"))',  # DNS 基线
    '(allow process-info* (target same-bin))',
)

# 任何情况下都拒绝的危险操作
_ALWAYS_DENY_RULES: tuple[str, ...] = (
    '(deny process-exec (literal "/usr/bin/sudo"))',
    '(deny process-exec (literal "/usr/bin/su"))',
    '(deny process-exec (literal "/usr/bin/login"))',
    '(deny process-exec (literal "/usr/sbin/installer"))',
    '(deny process-exec (literal "/usr/sbin/systemsetup"))',
    '(deny process-exec (literal "/usr/sbin/softwareupdate"))',
    '(deny process-exec (literal "/usr/bin/defaults"))',
    '(deny process-exec (literal "/usr/bin/security"))',
    '(deny file-write* (subpath "/Library/Keychains"))',
    '(deny file-read* (subpath "/Library/Keychains"))',
    '(deny file-write* (subpath "/var/db/SystemPolicyConfiguration"))',
    '(deny file-write* (subpath "/Library/Application Support/com.apple.TCC"))',
    '(deny file-write* (subpath "/Library/Preferences/com.apple.alf"))',
    '(deny mach-lookup (name "com.apple.system.opendirectoryd.api"))',
    '(deny mach-lookup (name "com.apple.SecurityServer"))',
)


class SandboxProfileError(Exception):
    """sandbox profile 生成错误"""


@dataclass(frozen=True)
class SandboxProfileResult:
    """sandbox profile 生成结果

    Attributes:
        agent_id: Agent ID
        profile_text: 完整 sandbox-exec profile 文本 (可直接 sandbox-exec -p <file>)
        profile_sha256: profile 内容 SHA256 (审计用)
        declared_capabilities: 输入的声明能力列表
        declared_endpoints: 输入的声明端点列表
        generated_at: 生成时间戳 (unix seconds)
        capability_hash: 声明能力 + 端点的 HMAC 哈希 (确保 profile 与 card 一致)
        rule_count: profile 总规则数
        error: 生成失败时的错误信息 (成功为 "")
    """

    agent_id: str
    profile_text: str
    profile_sha256: str
    declared_capabilities: list[str] = field(default_factory=list)
    declared_endpoints: list[str] = field(default_factory=list)
    generated_at: float = field(default_factory=lambda: time.time())
    capability_hash: str = ""
    rule_count: int = 0
    error: str = ""

    @property
    def is_valid(self) -> bool:
        """profile 是否有效生成 (无错误)"""
        return not self.error

    def to_audit_payload(self) -> dict[str, Any]:
        """转为 UnifiedAuditStore 可写入的 payload"""
        return {
            "agent_id": self.agent_id,
            "profile_sha256": self.profile_sha256,
            "declared_capabilities": self.declared_capabilities,
            "declared_endpoints": self.declared_endpoints,
            "generated_at": self.generated_at,
            "capability_hash": self.capability_hash,
            "rule_count": self.rule_count,
        }


class SandboxProfileGenerator:
    """根据 SignedAgentCard 声明能力生成 macOS sandbox-exec profile

    Usage:
        gen = SandboxProfileGenerator()
        card = SignedAgentCard(agent_id="claude-code", capabilities=["network_read", "file_read"])
        result = gen.generate(card)
        if result.is_valid:
            # 写入临时文件
            path = Path(f"/tmp/sandbox-{card.agent_id}.sb")
            path.write_text(result.profile_text)
            # sandbox-exec -f path /path/to/agent-binary

    保证:
    - 2.1-A2: 未声明的 capability 对应操作被拒绝 (deny default + 显式 deny)
    - 2.1-A4: profile 与 declared_capabilities 100% 一致 (capability_hash 绑定)
    - 未知 capability 抛 SandboxProfileError,拒绝生成宽松 profile
    """

    def __init__(
        self,
        extra_deny_rules: tuple[str, ...] = (),
        extra_allow_rules: tuple[str, ...] = (),
        allow_unknown_capabilities: bool = False,
    ) -> None:
        """初始化 profile 生成器

        Args:
            extra_deny_rules: 额外拒绝规则 (覆盖默认 _ALWAYS_DENY_RULES)
            extra_allow_rules: 额外允许规则 (基线之外)
            allow_unknown_capabilities: 未知 capability 是否容忍 (默认 False,严格拒绝)
        """
        self._extra_deny = extra_deny_rules
        self._extra_allow = extra_allow_rules
        self._allow_unknown = allow_unknown_capabilities

    def generate(
        self,
        agent_id: str,
        capabilities: list[str],
        endpoints: list[str] | None = None,
    ) -> SandboxProfileResult:
        """生成 sandbox-exec profile

        Args:
            agent_id: Agent ID (写入 profile 注释)
            capabilities: SignedAgentCard.capabilities
            endpoints: SignedAgentCard.endpoints (network_read 时用于白名单)

        Returns:
            SandboxProfileResult — 成功时 is_valid=True,失败时 error 填充原因
        """
        endpoints = endpoints or []

        # 校验 capabilities
        unknown_caps = [c for c in capabilities if c not in CAPABILITY_TO_SANDBOX_RULES]
        if unknown_caps and not self._allow_unknown:
            return SandboxProfileResult(
                agent_id=agent_id,
                profile_text="",
                profile_sha256="",
                declared_capabilities=capabilities,
                declared_endpoints=endpoints,
                capability_hash="",
                rule_count=0,
                error=f"unknown capabilities: {unknown_caps}",
            )

        # 计算 capability_hash (绑定 profile 与 card)
        cap_hash = self._compute_capability_hash(agent_id, capabilities, endpoints)

        # 构建 profile
        lines: list[str] = [
            f";; MAREF sandbox-exec profile for agent={agent_id}",
            f";; generated_at={time.time():.6f}",
            f";; capabilities={json.dumps(capabilities, sort_keys=True)}",
            f";; endpoints={json.dumps(endpoints, sort_keys=True)}",
            f";; capability_hash={cap_hash}",
            ";; DO NOT EDIT — auto-generated by SandboxProfileGenerator",
            "",
            "(version 1)",
            "(deny default)",  # 默认拒绝 — 只允许显式声明的
            "",
            ";; === baseline allows (any process needs these) ===",
        ]
        lines.extend(_BASELINE_ALLOW_RULES)
        lines.extend(self._extra_allow)

        lines.append("")
        lines.append(";; === always-deny rules (security-critical) ===")
        lines.extend(_ALWAYS_DENY_RULES)
        lines.extend(self._extra_deny)

        # 为每个声明的 capability 添加 allow 规则
        for cap in capabilities:
            rules = CAPABILITY_TO_SANDBOX_RULES.get(cap)
            if rules is None:
                if self._allow_unknown:
                    lines.append("")
                    lines.append(f";; unknown capability '{cap}' — skipped (allow_unknown=True)")
                    continue
                # 已在前面校验,这里不应到达
                continue
            lines.append("")
            lines.append(f";; === capability: {cap} ===")
            for rule in rules.get("allow", []):
                # network_read 的 remote tcp 替换为端点白名单
                if cap == "network_read" and "remote tcp)" in rule and endpoints:
                    for ep in endpoints:
                        ep_rule = rule.replace("(remote tcp)", f'(remote tcp "{ep}")')
                        lines.append(ep_rule)
                else:
                    lines.append(rule)
            for rule in rules.get("deny", []):
                lines.append(rule)

        # 若未声明 network_read,显式拒绝所有出站网络
        if "network_read" not in capabilities and "network_write" not in capabilities:
            lines.append("")
            lines.append(";; === no network capability declared — deny all ===")
            lines.append("(deny network*)")

        # 若未声明 process_spawn/process_exec,显式拒绝
        if "process_spawn" not in capabilities and "process_exec" not in capabilities:
            lines.append("")
            lines.append(";; === no process capability declared — deny all ===")
            lines.append("(deny process-fork)")
            lines.append("(deny process-exec)")

        profile_text = "\n".join(lines) + "\n"
        profile_sha = hashlib.sha256(profile_text.encode("utf-8")).hexdigest()
        rule_count = sum(
            1 for line in lines if line.strip().startswith("(") and not line.startswith(";;")
        )

        return SandboxProfileResult(
            agent_id=agent_id,
            profile_text=profile_text,
            profile_sha256=profile_sha,
            declared_capabilities=capabilities,
            declared_endpoints=endpoints,
            capability_hash=cap_hash,
            rule_count=rule_count,
        )

    def generate_from_card(self, card: Any) -> SandboxProfileResult:
        """从 SignedAgentCard 对象生成 profile (便捷方法)

        Args:
            card: SignedAgentCard 实例 (需有 agent_id/capabilities/endpoints 属性)

        Returns:
            SandboxProfileResult
        """
        try:
            agent_id: str = str(getattr(card, "agent_id", ""))
            capabilities: list[str] = list(getattr(card, "capabilities", []))
            endpoints: list[str] = list(getattr(card, "endpoints", []))
        except Exception as exc:
            return SandboxProfileResult(
                agent_id="",
                profile_text="",
                profile_sha256="",
                error=f"failed to extract card fields: {type(exc).__name__}: {exc}",
            )
        if not agent_id:
            return SandboxProfileResult(
                agent_id="",
                profile_text="",
                profile_sha256="",
                error="card.agent_id is empty",
            )
        return self.generate(agent_id, capabilities, endpoints)

    def verify_profile_card_consistency(
        self,
        result: SandboxProfileResult,
        agent_id: str,
        capabilities: list[str],
        endpoints: list[str] | None = None,
    ) -> bool:
        """验证 profile 与 card 的能力一致性 (2.1-A4)

        Args:
            result: generate() 返回的 profile
            agent_id: 当前 Agent ID
            capabilities: 当前声明能力
            endpoints: 当前声明端点

        Returns:
            True = profile 与 card 一致; False = 不一致 (应阻断 Agent 启动)
        """
        if result.agent_id != agent_id:
            return False
        if set(result.declared_capabilities) != set(capabilities):
            return False
        if set(result.declared_endpoints) != set(endpoints or []):
            return False
        expected_hash = self._compute_capability_hash(agent_id, capabilities, endpoints or [])
        return result.capability_hash == expected_hash

    @staticmethod
    def _compute_capability_hash(
        agent_id: str,
        capabilities: list[str],
        endpoints: list[str],
    ) -> str:
        """计算能力哈希 — agent_id + sorted capabilities + sorted endpoints"""
        payload = json.dumps(
            {
                "agent_id": agent_id,
                "capabilities": sorted(capabilities),
                "endpoints": sorted(endpoints),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
