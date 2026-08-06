"""
Probe 抽象基类 — 所有具体 Probe 必须继承

生命周期:
    probe = ProcessProbe(config=ProbeConfig(poll_interval=0.5))
    await probe.start()          # 初始化资源
    events = await probe.poll()  # 周期性调用,返回观测到的事件
    await probe.stop()           # 释放资源

Probe 不直接推送事件到 Daemon,而是由 Daemon 的 poll loop 周期性调用 poll()
拉取事件。这样设计是为了:
1. Daemon 控制轮询节奏 (避免 Probe 各自为政导致 CPU 飙升)
2. Probe 无需持有 Daemon 引用,降低耦合
3. 测试时可直接调用 poll() 验证检测逻辑,无需启动整个 Daemon
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from maref.sentinel.event import ObservationEvent


@dataclass(frozen=True)
class ProbeConfig:
    """Probe 配置 — 不可变,运行时不修改

    Attributes:
        poll_interval: 轮询间隔 (秒),Daemon 按此间隔调用 poll()
        target_pids: 目标进程 ID列表 (空 = 监控全部 Agent 进程,M1 暂不实现自动发现)
        target_agent_ids: 目标 Agent ID 列表 (从 SignedAgentCard 解析,M4 接入)
        hmac_key: HMAC-SHA256 签名密钥 (从 KeyringStore 获取)
        sensitive_paths: 敏感文件路径列表 (FileProbe/TimezoneProbe 用)
        sensitive_env_vars: 敏感环境变量名列表 (EnvProbe 用)
    """

    poll_interval: float = 1.0
    target_pids: tuple[int, ...] = ()
    target_agent_ids: tuple[str, ...] = ()
    hmac_key: bytes = b""
    sensitive_paths: tuple[str, ...] = (
        "/etc/localtime",
        "/etc/timezone",
        "~/.ssh/id_rsa",
        "~/.ssh/id_ed25519",
        "~/.aws/credentials",
        "~/.config/gcloud/credentials.db",
    )
    sensitive_env_vars: tuple[str, ...] = (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "TZ",
    )


class Probe(ABC):
    """Probe 抽象基类 — 所有具体 Probe 必须继承

    子类必须实现:
        - probe_name 属性: 返回 Probe 名称 (process|env|file|timezone|...)
        - start(): 初始化资源 (打开文件/建立连接/加载规则)
        - poll(): 执行一次检测,返回观测到的事件列表 (可能为空)
        - stop(): 释放资源

    子类可选实现:
        - health_check(): 健康检查 (默认返回 True)
    """

    @property
    @abstractmethod
    def probe_name(self) -> str:
        """Probe 名称 — 用于 ObservationEvent.source 字段"""
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        """初始化 Probe 资源。幂等: 重复调用无副作用。"""
        raise NotImplementedError

    @abstractmethod
    async def poll(self) -> list[ObservationEvent]:
        """执行一次检测,返回观测到的事件列表。

        Returns:
            观测事件列表 (可能为空)。每个事件必须已通过 with_hash() 签名。
            Daemon 会周期性调用此方法,间隔由 ProbeConfig.poll_interval 决定。
        """
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """释放 Probe 资源。幂等: 重复调用无副作用。"""
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Probe 健康检查 — 默认返回 True,子类可覆盖"""
        return True
