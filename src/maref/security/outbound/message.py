"""OutboundMessage — 出站消息模型 (v0.52.1 G3-A1)。

描述 agent 向外部主体发起的出站通信。所有字段经 pydantic 风格校验
(dataclass + __post_init__)，作为 ``OutboundMessageGate`` 的输入。

设计要点:
- recipient_type 区分"外部人类 / 第三方系统 / 外部代理"——社交工程只针对人类
- channel 区分传输渠道——文件传输等高危渠道影响门禁阈值
- declared_purpose 是 agent 声明的发送意图，用于与门禁裁决比对
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OutboundChannel(str, Enum):
    """出站传输渠道枚举。"""

    MCP = "mcp"  # MCP 协议调用
    A2A = "a2a"  # A2A 代理到代理
    TOOL = "tool"  # 通用工具调用 (email/slack/discord 等由 tool 封装)
    EMAIL = "email"
    SLACK = "slack"
    DISCORD = "discord"
    FILE_TRANSFER = "file_transfer"  # 在线文件传输服务 (AISI 场景直接命中)
    HTTP = "http"  # 原始 HTTP 出站请求
    OTHER = "other"


class RecipientType(str, Enum):
    """接收方类型枚举。"""

    HUMAN = "human"  # 外部真实人类 (社交工程风险)
    THIRD_PARTY_SYSTEM = "third_party_system"  # 第三方系统/服务
    THIRD_PARTY_AGENT = "third_party_agent"  # 外部 AI 代理
    UNKNOWN = "unknown"


@dataclass
class OutboundAttachment:
    """出站消息附件元数据。

    Attributes:
        filename: 附件文件名。
        content_type: MIME 类型 (可为空)。
        size_bytes: 附件大小 (字节)。
        content: 附件内容摘要/前 N 字节 (默认保留头部用于载荷检测)。
        is_archive: 是否为压缩包 (zip/tar/gz)。
    """

    filename: str = ""
    content_type: str = ""
    size_bytes: int = 0
    content: bytes = b""
    is_archive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "is_archive": self.is_archive,
        }


@dataclass
class OutboundMessage:
    """出站消息模型。

    Attributes:
        sender_agent_id: 发送方 Agent ID。
        recipient: 接收方地址 (邮箱/用户名/URL)。
        recipient_type: 接收方类型 (human 触发社交工程检测)。
        channel: 传输渠道。
        body: 消息正文。
        attachments: 附件列表。
        declared_purpose: agent 声明的发送意图 (HITL 展示用)。
        created_at: 创建时间戳。
        message_id: 消息唯一标识 (UUID)。
        agent_intent: 可选。与意图推理 (G2) 联动的结构化意图描述。
    """

    sender_agent_id: str
    recipient: str
    body: str = ""
    recipient_type: RecipientType = RecipientType.UNKNOWN
    channel: OutboundChannel = OutboundChannel.OTHER
    attachments: list[OutboundAttachment] = field(default_factory=list)
    declared_purpose: str = ""
    created_at: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_intent: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sender_agent_id:
            raise ValueError("sender_agent_id 不能为空")
        if not self.recipient:
            raise ValueError("recipient 不能为空")
        if isinstance(self.recipient_type, str):
            self.recipient_type = RecipientType(self.recipient_type)
        if isinstance(self.channel, str):
            self.channel = OutboundChannel(self.channel)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender_agent_id": self.sender_agent_id,
            "recipient": self.recipient,
            "recipient_type": self.recipient_type.value,
            "channel": self.channel.value,
            "body": self.body,
            "attachments": [a.to_dict() for a in self.attachments],
            "declared_purpose": self.declared_purpose,
            "created_at": self.created_at,
            "agent_intent": self.agent_intent,
        }
