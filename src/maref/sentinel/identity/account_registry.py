"""ExternalAccountRegistry — 外部账号登记表 (v0.52.1 G1-B1)。

登记 agent 在外部平台 (GitHub 等) 使用的身份。核心治理语义:
**使用外部身份前必须登记** — 未登记即使用 → capability drift (与
``sentinel/drift/capability_drift_detector.py`` 的"声明 vs 实际"一致)。

关键概念:
- ``declared``: 该账号是否由所属 agent 声明 (经 SignedAgentCard 或人工确认)
- 未声明账号 (declared=False) 是身份伪造 (IDENTITY_SPOOFING) 的首要信号
- 同一 agent 短窗口注册多账号 → SybilDetector 消费
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlatformType(str, Enum):
    """外部平台类型枚举。"""

    GITHUB = "github"
    GITLAB = "gitlab"
    HUGGINGFACE = "huggingface"
    SLACK = "slack"
    DISCORD = "discord"
    EMAIL = "email"
    FILE_TRANSFER = "file_transfer"  # 在线文件传输服务 (AISI 场景)
    FORUM = "forum"
    OTHER = "other"


@dataclass
class ExternalAccount:
    """外部平台账号记录。

    Attributes:
        account_id: 内部唯一标识。
        platform: 平台类型。
        handle: 外部账号名/句柄。
        agent_did: 使用该账号的系统内 Agent DID。
        declared: 是否经 agent 声明/人工确认。
        first_seen: 首次观测时间戳。
        last_seen: 最近活跃时间戳。
        ip_hash: 网络出口指纹 (IP 哈希, 脱敏)。
        ua_hash: 客户端指纹 (UA 哈希, 脱敏)。
        profile_id: 关联的行为指纹 Profile ID (fingerprint.py)。
        metadata: 平台侧附加信息。
    """

    account_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    platform: PlatformType = PlatformType.OTHER
    handle: str = ""
    agent_did: str = ""
    declared: bool = False
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    ip_hash: str = ""
    ua_hash: str = ""
    profile_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "platform": self.platform.value,
            "handle": self.handle,
            "agent_did": self.agent_did,
            "declared": self.declared,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "ip_hash": self.ip_hash,
            "ua_hash": self.ua_hash,
            "profile_id": self.profile_id,
            "metadata": self.metadata,
        }


class ExternalAccountRegistry:
    """外部账号登记表。

    Usage::

        registry = ExternalAccountRegistry()
        registry.register(ExternalAccount(platform=PlatformType.GITHUB,
                                          handle="dev-x", agent_did="agent-01"))
        undeclared = registry.undeclared_accounts()  # 未声明账号 → 漂移信号
    """

    def __init__(self) -> None:
        self._accounts: dict[str, ExternalAccount] = {}
        self._handle_index: dict[tuple[str, str], str] = {}  # (platform, handle) -> account_id
        self._agent_index: dict[str, list[str]] = {}  # agent_did -> [account_id]
        # 使用历史: (platform, handle) -> set[agent_did] — 记录所有使用过该外部
        # 身份的系统内 agent (G1-C3 修复: 跨代理共享检测的数据基础)。
        self._usage_history: dict[tuple[str, str], set[str]] = {}

    def register(self, account: ExternalAccount) -> ExternalAccount:
        """登记外部账号 (幂等: 同一 platform+handle 更新, 不重复)。

        幂等语义下的多 agent 使用: 同 handle 被第二个 agent 登记时, 不覆盖
        原记录, 而是把该 agent 记入使用历史 ``_usage_history``, 供跨代理
        共享检测 (CollusionDetector) 消费。

        Args:
            account: 待登记账号。

        Returns:
            登记后的账号记录 (可能为已存在的同 handle 记录)。
        """
        if isinstance(account.platform, str):
            account.platform = PlatformType(account.platform)
        key = (account.platform.value, account.handle.lower())
        # 记录使用历史 (对幂等命中与新建都生效)
        if account.agent_did:
            self._usage_history.setdefault(key, set()).add(account.agent_did)
        existing_id = self._handle_index.get(key)
        if existing_id:
            existing = self._accounts[existing_id]
            existing.last_seen = time.time()
            # 首次登记记录归属; 后续 agent 使用不覆盖, 保留首个声明者
            if not existing.agent_did:
                existing.agent_did = account.agent_did
            # 同步 agent 索引 (G1-C3 修复: 消除 list_by_agent 索引不一致)
            if account.agent_did:
                agent_ids = self._agent_index.setdefault(account.agent_did, [])
                if existing.account_id not in agent_ids:
                    agent_ids.append(existing.account_id)
            return existing
        self._accounts[account.account_id] = account
        self._handle_index[key] = account.account_id
        if account.agent_did:
            self._agent_index.setdefault(account.agent_did, []).append(account.account_id)
        return account

    def get(self, platform: PlatformType, handle: str) -> ExternalAccount | None:
        """按 platform+handle 查询账号。"""
        key = (platform.value, handle.lower())
        account_id = self._handle_index.get(key)
        if account_id is None:
            return None
        return self._accounts.get(account_id)

    def get_by_id(self, account_id: str) -> ExternalAccount | None:
        return self._accounts.get(account_id)

    def list_by_agent(self, agent_did: str) -> list[ExternalAccount]:
        """列出某 agent 登记/使用过的全部外部账号。"""
        ids = self._agent_index.get(agent_did, [])
        return [self._accounts[i] for i in ids if i in self._accounts]

    def agents_using(self, platform: PlatformType, handle: str) -> set[str]:
        """返回使用过该外部身份的全部 agent DID (跨代理共享检测用)。"""
        key = (platform.value, handle.lower())
        return set(self._usage_history.get(key, set()))

    def all_usage(self) -> dict[tuple[str, str], set[str]]:
        """返回全部 (platform, handle) -> 使用它的 agent DID 集合。"""
        return {k: set(v) for k, v in self._usage_history.items()}

    def undeclared_accounts(self) -> list[ExternalAccount]:
        """列出未声明 (declared=False) 的外部账号 — 身份伪造首要信号。"""
        return [a for a in self._accounts.values() if not a.declared]

    def mark_declared(self, platform: PlatformType, handle: str) -> bool:
        """人工/权威确认后标记账号为已声明。"""
        account = self.get(platform, handle)
        if account is None:
            return False
        account.declared = True
        return True

    def touch(self, account_id: str) -> None:
        """刷新账号活跃时间。"""
        account = self._accounts.get(account_id)
        if account is not None:
            account.last_seen = time.time()

    def all_accounts(self) -> list[ExternalAccount]:
        return list(self._accounts.values())

    def count(self) -> int:
        return len(self._accounts)
