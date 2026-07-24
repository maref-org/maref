"""GaaS TrustScore Service — multi-tenant trust graph interface.

Wraps the existing TrustAPI with tenant isolation.
Each tenant gets an independent TrustGraph instance.
"""

from __future__ import annotations

from typing import Any

from maref.security.trust_api import TrustAPI
from maref.security.trust_graph import TrustGraph


class TrustScoreService:
    """Tenant-isolated trust score service.

    Maintains a separate TrustGraph per tenant for data isolation.
    """

    def __init__(self) -> None:
        self._graphs: dict[str, TrustGraph] = {}
        self._apis: dict[str, TrustAPI] = {}

    def _get_or_create(self, tenant_id: str) -> TrustAPI:
        if tenant_id not in self._apis:
            graph = TrustGraph()
            self._graphs[tenant_id] = graph
            self._apis[tenant_id] = TrustAPI(graph)
        return self._apis[tenant_id]

    def get_score(self, tenant_id: str, agent_id: str) -> float | None:
        """Get trust score for an agent in a tenant."""
        api = self._get_or_create(tenant_id)
        return api.trust_score(agent_id)

    def set_score(
        self,
        tenant_id: str,
        agent_id: str,
        score: float,
        reason: str = "",
    ) -> None:
        """Set trust score for an agent."""
        api = self._get_or_create(tenant_id)
        api.set_trust(agent_id, score, reason)

    def get_report(self, tenant_id: str, agent_id: str) -> dict[str, Any]:
        """Get full trust report for an agent."""
        api = self._get_or_create(tenant_id)
        return api.get_trust_report(agent_id)

    def list_agents(self, tenant_id: str) -> list[str]:
        """List all agents in a tenant."""
        api = self._get_or_create(tenant_id)
        return api.list_agents()

    def get_history(self, tenant_id: str, agent_id: str) -> list[dict[str, Any]]:
        """Get trust score history for an agent."""
        api = self._get_or_create(tenant_id)
        return api.get_trust_history(agent_id)

    def fuse_from_mapping(self, mapping_path: str, tenant_id: str = "default") -> int:
        """Import trust scores from external_agent_mapping.json into TrustGraph.

        Reads the mapping file and updates or creates trust score entries
        for each agent. Only updates if the mapping's computed_at is newer.

        Returns:
            Number of agents imported/updated.
        """
        import json
        from pathlib import Path

        mapping_file = Path(mapping_path)
        if not mapping_file.exists():
            return 0

        try:
            data = json.loads(mapping_file.read_text())
        except (json.JSONDecodeError, OSError):
            return 0

        agents = data.get("external_agents", {})
        updated_at = data.get("updated_at", "")
        api = self._get_or_create(tenant_id)
        count = 0

        for agent_id, info in agents.items():
            # 取最高可用评分
            score = info.get("dynamic_trust_score") or info.get("trust_score", 0.5)
            trust_level = info.get("trust_level", "UNTRUSTED")

            # 归一化到 TrustGraph 的 0-100 范围（如果 mapping 是 0-1）
            if isinstance(score, float) and score <= 1.0:
                score = score * 100

            current = api.trust_score(agent_id)
            if current is not None and current >= score:
                continue  # 已有更高评分，不降级

            reason = f"fuse_from_mapping (level={trust_level}, source_updated={updated_at})"
            api.set_trust(agent_id, min(100.0, max(0.0, score)), reason)
            count += 1

        return count

    def decay_scores(self, tenant_id: str, decay_factor: float = 0.99) -> None:
        """Apply time-based decay to all scores in a tenant."""
        api = self._get_or_create(tenant_id)
        for agent_id in api.list_agents():
            current = api.trust_score(agent_id)
            if current is not None:
                new_score = current * decay_factor
                api.set_trust(agent_id, new_score, reason="time_decay")
