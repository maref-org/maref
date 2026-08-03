"""Agent DNS — DID 到能力目录的解析服务（方案 E M2）。

建立 Agent 互联网的"身份 → 能力"解析：通过 DID 可查询一个 agent 的
能力目录（Agent Card，对齐 A2A Agent Card 结构）。DID 被撤销/注销后
解析返回失败，与 :class:`~maref.identity.did_registry.DIDRegistry` 的
版本化生命周期联动。

设计: docs/plans/2026-08-01-agent-war-governance-design.md 方案 E
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.identity.did_registry import AgentDID, DIDRegistry


@dataclass
class AgentCard:
    """Agent 能力目录卡（对齐 A2A Agent Card 结构）。

    Attributes:
        did: 对应的 DID。
        name: agent 名称。
        description: 能力描述。
        skills: 技能清单（对齐 A2A skills 数组）。
        endpoints: 服务端点列表。
        capabilities: 能力标志（streaming/pushNotifications 等）。
        version: Agent Card 版本。
        registered_at: 注册时间。
        updated_at: 最后更新时间。
        status: active / revoked / deactivated（派生自 DID 生命周期）。
    """

    did: AgentDID
    name: str
    description: str
    skills: list[dict[str, Any]] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    registered_at: float = 0.0
    updated_at: float = 0.0
    status: str = "active"

    def to_a2a_card(self, base_url: str = "") -> dict[str, Any]:
        """转为 A2A Agent Card JSON（可发布到 ``/.well-known/agent-card.json``）。

        ``url`` 取第一个 endpoint（无则用 base_url 占位）。
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.endpoints[0] if self.endpoints else base_url,
            "protocolVersion": "1.0",
            "capabilities": dict(self.capabilities),
            "skills": [dict(s) for s in self.skills],
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["application/json"],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "did": self.did.did_string,
            "name": self.name,
            "description": self.description,
            "skills": [dict(s) for s in self.skills],
            "endpoints": list(self.endpoints),
            "capabilities": dict(self.capabilities),
            "version": self.version,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentCard:
        return cls(
            did=AgentDID.parse(data["did"]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            skills=list(data.get("skills", [])),
            endpoints=list(data.get("endpoints", [])),
            capabilities=dict(data.get("capabilities", {})),
            version=data.get("version", "1.0.0"),
            registered_at=float(data.get("registered_at", 0.0)),
            updated_at=float(data.get("updated_at", 0.0)),
            status=data.get("status", "active"),
        )


class AgentDNS:
    """Agent 互联网的 DID → Agent Card 解析服务。

    与 :class:`DIDRegistry` 联动：解析时校验 DID 生命周期状态，
    revoked/deactivated 的 DID 解析失败。
    """

    def __init__(
        self,
        did_registry: DIDRegistry | None = None,
    ) -> None:
        self._did_registry = did_registry or DIDRegistry()
        self._cards: dict[AgentDID, AgentCard] = {}

    # -- 注册 --

    def register(
        self,
        did: AgentDID,
        name: str,
        description: str,
        skills: list[dict[str, Any]] | None = None,
        endpoints: list[str] | None = None,
        capabilities: dict[str, Any] | None = None,
        version: str = "1.0.0",
        require_registered: bool = True,
    ) -> AgentCard:
        """注册/更新一个 agent 的能力目录。

        Args:
            did: agent 的 DID。
            name: agent 名称。
            description: 能力描述。
            skills: 技能清单（对齐 A2A skills）。
            endpoints: 服务端点。
            capabilities: 能力标志。
            version: Agent Card 版本。
            require_registered: True 时要求 DID 已在 DIDRegistry 注册，
                否则该 agent 无可验证身份，拒绝挂牌（防无身份 agent 冒名）。
        """
        record = self._did_registry.resolve(did)
        if require_registered and record is None:
            raise ValueError(f"DID {did.did_string} 未在 DIDRegistry 注册，拒绝挂牌")
        if record is not None and not self._did_registry.is_active(did):
            raise ValueError(f"DID {did.did_string} 生命周期状态为 {record.status}，拒绝挂牌")

        now = time.time()
        existing = self._cards.get(did)
        card = AgentCard(
            did=did,
            name=name,
            description=description,
            skills=list(skills or []),
            endpoints=list(endpoints or []),
            capabilities=dict(capabilities or {}),
            version=version,
            registered_at=existing.registered_at if existing else now,
            updated_at=now,
            status="active",
        )
        self._cards[did] = card
        return card

    # -- 解析 --

    def resolve(self, did: AgentDID) -> AgentCard | None:
        """解析 DID → Agent Card。

        未注册或 DID 已 revoked/deactivated 时返回 None。
        """
        card = self._cards.get(did)
        if card is None:
            return None
        # 与 DIDRegistry 生命周期联动：身份已撤销则能力目录失效。
        record = self._did_registry.resolve(did)
        if record is not None and record.status != "active":
            return None
        return card

    def resolve_did_string(self, did_string: str) -> AgentCard | None:
        """按 DID 字符串解析（对协议层友好）。"""
        try:
            did = AgentDID.parse(did_string)
        except ValueError:
            return None
        return self.resolve(did)

    # -- 注销 --

    def unregister(self, did: AgentDID) -> AgentCard | None:
        """注销能力目录（从 DNS 移除）。DID 本身不删除，保留在 DIDRegistry。"""
        return self._cards.pop(did, None)

    def unregister_did_string(self, did_string: str) -> AgentCard | None:
        try:
            did = AgentDID.parse(did_string)
        except ValueError:
            return None
        return self.unregister(did)

    # -- 查询 --

    def list_cards(self, active_only: bool = True) -> list[AgentCard]:
        """列出已注册的 Agent Card（默认仅 active）。"""
        cards: list[AgentCard] = []
        for did, card in self._cards.items():
            if not active_only:
                cards.append(card)
                continue
            record = self._did_registry.resolve(did)
            if record is None or record.status == "active":
                cards.append(card)
        return sorted(cards, key=lambda c: c.did.did_string)

    def count(self) -> int:
        return len(self._cards)

    # -- 持久化 --

    def to_dict(self) -> dict[str, Any]:
        return {
            "cards": {did.did_string: card.to_dict() for did, card in self._cards.items()}
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentDNS:
        dns = cls()
        for _, card_data in data.get("cards", {}).items():
            card = AgentCard.from_dict(card_data)
            dns._cards[card.did] = card
        return dns


__all__ = ["AgentCard", "AgentDNS"]
