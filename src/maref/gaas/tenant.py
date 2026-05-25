"""GaaS Tenant Manager — multi-tenant isolation and authentication.

Supports JWT + API Key dual-mode auth with tenant-scoped resource access.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Tenant:
    """A GaaS tenant with isolation boundaries."""

    tenant_id: str
    name: str
    tier: str = "free"  # free | pro | business | enterprise
    created_at: float = field(default_factory=time.time)
    api_key_hash: str = ""
    jwt_secret: str = field(default_factory=lambda: secrets.token_hex(32))
    quota: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.quota:
            self.quota = {
                "max_agents": 1 if self.tier == "free" else 10 if self.tier == "pro" else 100 if self.tier == "business" else -1,
                "max_checks_per_month": 1000 if self.tier == "free" else 100_000 if self.tier == "pro" else 1_000_000 if self.tier == "business" else -1,
                "audit_retention_days": 7 if self.tier == "free" else 90 if self.tier == "pro" else 365 if self.tier == "business" else 2555,
                "hitl_enabled": self.tier != "free",
                "federation_enabled": self.tier == "enterprise",
            }


class TenantManager:
    """In-memory tenant registry with API key validation.

    Production should use Redis/Postgres for persistence.
    """

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._api_key_to_tenant: dict[str, str] = {}

    def register(self, tenant: Tenant, api_key: str | None = None) -> str:
        """Register a tenant. Returns API key if not provided."""
        if tenant.tenant_id in self._tenants:
            raise ValueError(f"Tenant {tenant.tenant_id} already exists")

        self._tenants[tenant.tenant_id] = tenant

        if api_key is None:
            api_key = f"mk_{secrets.token_urlsafe(32)}"
        self._api_key_to_tenant[api_key] = tenant.tenant_id
        tenant.api_key_hash = api_key  # Store plaintext for MVP; hash in production
        return api_key

    def get_by_id(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def get_by_api_key(self, api_key: str) -> Tenant | None:
        tenant_id = self._api_key_to_tenant.get(api_key)
        if tenant_id:
            return self._tenants.get(tenant_id)
        return None

    def check_quota(self, tenant_id: str, resource: str, current_usage: int) -> bool:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False
        limit = tenant.quota.get(resource, -1)
        if limit == -1:
            return True
        return current_usage < limit

    def list_tenants(self) -> list[Tenant]:
        return list(self._tenants.values())
