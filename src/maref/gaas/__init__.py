"""MAREF GaaS (Governance-as-a-Service) — Multi-tenant governance engine.

Provides external-facing governance APIs for any Agent system:
  - Governance checks (ALLOW | DENY | ASK_USER | DEFER)
  - CircuitBreaker as a Service
  - HITL as a Service
  - AuditLog as a Service
  - TrustScore as a Service

Architecture:
  Client Agent → GaaS API Gateway → Governance Router →
    → CircuitBreaker Pool → HITL Service → AuditLog Service → Trust Graph
"""

from __future__ import annotations

__version__ = "0.34.0-rc"
