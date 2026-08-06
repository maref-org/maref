"""OutboundGuard — 出站通道守卫挂接层 (v0.52.1 G3-A6)。

以装饰器/包装器模式将 ``OutboundMessageGate`` 挂接到 mcp/a2a/tool 出站通道，
**不侵入**现有 client 内部实现 (保持向后兼容与既有测试不变)。

用法::

    from maref.security.outbound import OutboundGuard

    guard = OutboundGuard(agent_id="agent-01")

    # 1. 通用出站发送包装 (任意 sender)
    guarded_send = guard.wrap_sender(send_fn)

    # 2. MCP 通道
    client = guard.wrap_mcp_client(mcp_client)

    # 3. A2A 通道
    a2a = guard.wrap_a2a_client(a2a_client)

    # 4. Tool 通道
    guarded_tool = guard.wrap_tool(tool)

设计:
- fail-closed: gate 判定 DENY 时抛 ``BlockedOutboundError``, 不调用底层 sender
- HITL 判定由调用方处理 (返回 verdict 供人工确认; 不自动放行)
- ``wrap_*`` 系列返回包装后的对象, 原对象不变, 可随时拆除
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from maref.security.outbound.gate import (
    BlockedOutboundError,
    GateDecision,
    HITLRequiredError,
    MalformedOutboundCallError,
    OutboundMessageGate,
    OutboundVerdict,
)
from maref.security.outbound.message import (
    OutboundAttachment,
    OutboundChannel,
    OutboundMessage,
    RecipientType,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OutboundGuard:
    """出站通道守卫 (聚合门禁 + 通道包装)。

    Attributes:
        gate: 底层的 OutboundMessageGate。
        agent_id: 默认发送方 Agent ID (wrap_* 未显式传入时使用)。
    """

    def __init__(
        self,
        gate: OutboundMessageGate | None = None,
        agent_id: str = "",
        allow_hitl_passthrough: bool = False,
    ) -> None:
        self.gate = gate or OutboundMessageGate()
        self.agent_id = agent_id
        # G3-C1 修复 (fail-closed): 默认 HITL 决策不得透传发送。仅当调用方
        # 显式配置 allow_hitl_passthrough=True (已实现外部人工确认机制) 才放行。
        self.allow_hitl_passthrough = allow_hitl_passthrough

    # -- 核心裁决 --

    def check(
        self,
        recipient: str,
        body: str = "",
        *,
        recipient_type: RecipientType = RecipientType.HUMAN,
        channel: OutboundChannel = OutboundChannel.OTHER,
        attachments: list[OutboundAttachment] | None = None,
        sender_agent_id: str | None = None,
        declared_purpose: str = "",
        agent_intent: dict[str, Any] | None = None,
    ) -> OutboundVerdict:
        """构建出站消息并执行门禁裁决 (供 wrap_* 与手动调用共用)。

        Returns:
            OutboundVerdict。调用方对 HITL 决策负责任 (升级人工确认)。
        """
        message = OutboundMessage(
            sender_agent_id=sender_agent_id or self.agent_id,
            recipient=recipient,
            body=body,
            recipient_type=recipient_type,
            channel=channel,
            attachments=attachments or [],
            declared_purpose=declared_purpose,
            agent_intent=agent_intent or {},
        )
        return self.gate.check(message)

    def ensure_allowed(self, verdict: OutboundVerdict) -> OutboundVerdict:
        """DENY 决策抛异常阻断; ALLOW/HITL 直接返回。

        兼容接口 (HITL 仍由调用方决定)。新代码应使用
        :meth:`ensure_sendable` (fail-closed)。

        Args:
            verdict: 门禁裁决。

        Returns:
            原 verdict。

        Raises:
            BlockedOutboundError: verdict.decision == DENY。
        """
        if verdict.decision == GateDecision.DENY:
            logger.warning(
                "outbound blocked: message=%s reasons=%s",
                verdict.message_id,
                verdict.reasons,
            )
            raise BlockedOutboundError(verdict)
        return verdict

    def ensure_sendable(self, verdict: OutboundVerdict) -> OutboundVerdict:
        """fail-closed 门禁: 仅 ALLOW (或显式放行 HITL) 才可发送。

        包装器统一使用本方法, 防止 HITL 决策被静默透传 (G3-C1 修复)。

        Args:
            verdict: 门禁裁决。

        Returns:
            原 verdict。

        Raises:
            BlockedOutboundError: verdict.decision == DENY。
            HITLRequiredError: verdict.decision == HITL 且未配置 passthrough。
        """
        if verdict.decision == GateDecision.DENY:
            logger.warning(
                "outbound blocked: message=%s reasons=%s",
                verdict.message_id,
                verdict.reasons,
            )
            raise BlockedOutboundError(verdict)
        if verdict.decision == GateDecision.HITL and not self.allow_hitl_passthrough:
            logger.warning(
                "outbound needs human approval: message=%s reasons=%s",
                verdict.message_id,
                verdict.reasons,
            )
            raise HITLRequiredError(verdict)
        return verdict

    # -- 通用 sender 包装 --

    def wrap_sender(
        self,
        sender: Callable[..., T] | Callable[..., Awaitable[T]],
        *,
        channel: OutboundChannel = OutboundChannel.OTHER,
        recipient_type: RecipientType = RecipientType.HUMAN,
        recipient_key: str = "recipient",
        body_key: str = "body",
        sender_agent_id: str | None = None,
    ) -> Callable[..., T] | Callable[..., Awaitable[T]]:
        """包装任意出站发送函数。

        Args:
            sender: 底层发送函数。
            channel: 渠道 (默认 OTHER)。
            recipient_type: 接收方类型。
            recipient_key: sender kwargs 中接收方参数的键名。
            body_key: sender kwargs 中正文参数的键名。
            sender_agent_id: 显式发送方 ID。

        Returns:
            包装后的发送函数 (签名与原函数一致)。
        """

        async def _awrap(**kwargs: Any) -> T:
            recipient = kwargs.get(recipient_key, "")
            body = kwargs.get(body_key, "")
            verdict = self.check(
                recipient=recipient,
                body=body,
                channel=channel,
                recipient_type=recipient_type,
                sender_agent_id=sender_agent_id,
            )
            self.ensure_sendable(verdict)
            coro = cast(Callable[..., Awaitable[T]], sender)
            return await coro(**kwargs)

        def _wrap(**kwargs: Any) -> T:
            recipient = kwargs.get(recipient_key, "")
            body = kwargs.get(body_key, "")
            verdict = self.check(
                recipient=recipient,
                body=body,
                channel=channel,
                recipient_type=recipient_type,
                sender_agent_id=sender_agent_id,
            )
            self.ensure_sendable(verdict)
            return cast(T, sender(**kwargs))

        if getattr(sender, "_is_coroutine", False):
            return _awrap
        import inspect

        if inspect.iscoroutinefunction(sender):
            return _awrap
        return _wrap

    # -- 通道专用包装 (可选挂接, 不修改原类) --

    def wrap_mcp_client(self, client: Any) -> Any:
        """包装 MCPClient: 对含出站通信的工具调用前置门禁。

        通过拦截 ``call_tool``, 当工具参数含 recipient 字段时执行门禁。
        纯侵入式包装 (monkey-patch 可逆), 不修改 MCPClient 类定义。
        """
        original = client.call_tool

        def guarded_call_tool(*args: Any, **kwargs: Any) -> Any:
            # G3-I12: 参数结构无法解析时 fail-closed, 不得静默透传。
            if "args" in kwargs:
                args_dict = kwargs["args"]
            elif len(args) > 2:
                args_dict = args[2]
            else:
                raise MalformedOutboundCallError(
                    f"call_tool 参数结构无法解析 (args={len(args)}, kwargs={sorted(kwargs)})"
                )
            if not isinstance(args_dict, dict):
                raise MalformedOutboundCallError(
                    f"call_tool args 非 dict: {type(args_dict).__name__}"
                )
            recipient = args_dict.get("recipient") or args_dict.get("to")
            if recipient:
                verdict = self.check(
                    recipient=str(recipient),
                    body=str(args_dict.get("text", "")),
                    channel=OutboundChannel.MCP,
                    sender_agent_id=kwargs.get("agent_id"),
                )
                self.ensure_sendable(verdict)
            return original(*args, **kwargs)

        client.call_tool = guarded_call_tool
        client._maref_outbound_guard = self
        return client

    def wrap_a2a_client(self, client: Any) -> Any:
        """包装 A2AClient: 对 ``send_task`` 前置门禁。

        接收方为外部 agent (RecipientType.THIRD_PARTY_AGENT)。
        """
        original = client.send_task

        async def guarded_send_task(*args: Any, **kwargs: Any) -> Any:
            agent_url = kwargs.get("agent_url") or (args[0] if args else "")
            payload = kwargs.get("payload") or (args[1] if len(args) > 1 else {})
            verdict = self.check(
                recipient=str(agent_url),
                body=str(payload),
                channel=OutboundChannel.A2A,
                recipient_type=RecipientType.THIRD_PARTY_AGENT,
                sender_agent_id=getattr(client, "_agent_id", None),
            )
            self.ensure_sendable(verdict)
            return await original(*args, **kwargs)

        client.send_task = guarded_send_task
        client._maref_outbound_guard = self
        return client

    def wrap_tool(self, tool: Any) -> Any:
        """包装 Tool: 对 ``execute`` 前置门禁。

        工具输入含 recipient/body 字段 (如 email/slack 发送类工具) 时执行门禁。
        """
        original = tool.execute

        async def guarded_execute(input_dict: dict[str, Any], context: Any) -> Any:
            recipient = input_dict.get("recipient") or input_dict.get("to")
            if recipient:
                verdict = self.check(
                    recipient=str(recipient),
                    body=str(input_dict.get("text") or input_dict.get("body") or ""),
                    channel=OutboundChannel.TOOL,
                    attachments=[
                        OutboundAttachment(
                            filename=str(a.get("filename", "")),
                            content_type=str(a.get("content_type", "")),
                            size_bytes=int(a.get("size_bytes", 0)),
                            content=bytes(a.get("content", b"")),
                        )
                        for a in (input_dict.get("attachments") or [])
                    ],
                )
                self.ensure_sendable(verdict)
            return await original(input_dict, context)

        tool.execute = guarded_execute
        return tool
