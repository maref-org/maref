"""GaaS Tenant Manager - multi-tenant isolation and authentication.

Supports JWT + API Key dual-mode auth with tenant-scoped resource access.
Optional SQLite persistence: pass ``db_path`` to ``TenantManager`` to
survive process restarts (uses :class:`maref.governance.db.DatabaseManager`).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.governance.db import DatabaseManager


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
                "max_agents": 1
                if self.tier == "free"
                else 10
                if self.tier == "pro"
                else 100
                if self.tier == "business"
                else -1,
                "max_checks_per_month": 1000
                if self.tier == "free"
                else 100_000
                if self.tier == "pro"
                else 1_000_000
                if self.tier == "business"
                else -1,
                "audit_retention_days": 7
                if self.tier == "free"
                else 90
                if self.tier == "pro"
                else 365
                if self.tier == "business"
                else 2555,
                "hitl_enabled": self.tier != "free",
                "federation_enabled": self.tier == "enterprise",
            }


class TenantManager:
    """Tenant registry with API key validation.

    By default operates in-memory.  Pass ``db_path`` to enable SQLite
    persistence; in persistent mode the database is the source of truth
    and state survives process restarts.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db: DatabaseManager | None = None
        if db_path is not None:
            self._db = DatabaseManager(db_path)
            self._init_schema()
        # In-memory caches only used when _db is None.
        self._tenants: dict[str, Tenant] = {}
        self._api_key_to_tenant: dict[str, str] = {}

    def _init_schema(self) -> None:
        assert self._db is not None
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id    TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                tier         TEXT NOT NULL DEFAULT 'free',
                created_at   REAL NOT NULL,
                api_key_hash TEXT NOT NULL,
                jwt_secret   TEXT NOT NULL,
                quota        TEXT NOT NULL,
                config       TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tenant_api_keys (
                key_hash  TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_api_keys_tenant
                ON tenant_api_keys(tenant_id);
            """
        )

    @staticmethod
    def _row_to_tenant(row: Any) -> Tenant:
        return Tenant(
            tenant_id=row["tenant_id"],
            name=row["name"],
            tier=row["tier"],
            created_at=row["created_at"],
            api_key_hash=row["api_key_hash"],
            jwt_secret=row["jwt_secret"],
            quota=json.loads(row["quota"]),
            config=json.loads(row["config"]),
        )

    def register(self, tenant: Tenant, api_key: str | None = None) -> str:
        """Register a tenant. Returns API key if not provided."""
        # Check duplicate first to preserve original error semantics.
        if self._db is not None:
            exists = self._db.fetchone(
                "SELECT 1 FROM tenants WHERE tenant_id = ?", (tenant.tenant_id,)
            )
            if exists:
                raise ValueError(f"Tenant {tenant.tenant_id} already exists")
        else:
            if tenant.tenant_id in self._tenants:
                raise ValueError(f"Tenant {tenant.tenant_id} already exists")

        if api_key is None:
            api_key = f"mk_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        tenant.api_key_hash = key_hash

        if self._db is not None:
            with self._db.connection() as conn:
                conn.execute(
                    "INSERT INTO tenants (tenant_id, name, tier, created_at, "
                    "api_key_hash, jwt_secret, quota, config) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tenant.tenant_id,
                        tenant.name,
                        tenant.tier,
                        tenant.created_at,
                        key_hash,
                        tenant.jwt_secret,
                        json.dumps(tenant.quota),
                        json.dumps(tenant.config),
                    ),
                )
                conn.execute(
                    "INSERT INTO tenant_api_keys (key_hash, tenant_id) VALUES (?, ?)",
                    (key_hash, tenant.tenant_id),
                )
                conn.commit()
        else:
            self._tenants[tenant.tenant_id] = tenant
            self._api_key_to_tenant[key_hash] = tenant.tenant_id
        return api_key

    def get_by_id(self, tenant_id: str) -> Tenant | None:
        if self._db is not None:
            row = self._db.fetchone(
                "SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)
            )
            return self._row_to_tenant(row) if row else None
        return self._tenants.get(tenant_id)

    def get_by_api_key(self, api_key: str) -> Tenant | None:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        if self._db is not None:
            row = self._db.fetchone(
                "SELECT t.* FROM tenants t JOIN tenant_api_keys k "
                "ON t.tenant_id = k.tenant_id WHERE k.key_hash = ?",
                (key_hash,),
            )
            return self._row_to_tenant(row) if row else None
        tenant_id = self._api_key_to_tenant.get(key_hash)
        if tenant_id:
            return self._tenants.get(tenant_id)
        return None

    def check_quota(self, tenant_id: str, resource: str, current_usage: int) -> bool:
        tenant = self.get_by_id(tenant_id)
        if not tenant:
            return False
        limit = tenant.quota.get(resource, -1)
        if limit == -1:
            return True
        return current_usage < limit

    def list_tenants(self) -> list[Tenant]:
        if self._db is not None:
            rows = self._db.fetchall("SELECT * FROM tenants ORDER BY created_at")
            return [self._row_to_tenant(r) for r in rows]
        return list(self._tenants.values())
