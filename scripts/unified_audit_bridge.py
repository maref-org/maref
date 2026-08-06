"""
Unified Audit Bridge — merges GaaS + MCP Guard audit data into Sidecar unified API.

Replaces the mock _audit_logs list in sidecar/server.py with real merged data.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from maref.gaas.audit_service import AuditLogService
from maref.gaas.api import get_audit_service, get_governance_router, get_trust_service, get_hitl_service


# MCP Guard audit log file path
MCP_GUARD_AUDIT_LOG = Path.home() / ".maref_mcp_guard_audit.log"

# Map MCP Guard tool names to readable actions
TOOL_LABEL = {
    "Write": "文件写入",
    "Read": "文件读取",
    "Edit": "文件编辑",
    "Bash": "命令执行",
    "Glob": "文件搜索",
    "Grep": "内容搜索",
}


def build_unified_audit_log(max_entries: int = 200) -> list[dict[str, Any]]:
    """Build unified audit log from all sources, newest first."""
    entries: list[dict[str, Any]] = []

    # 1. GaaS AuditLogService entries (real governance decisions)
    _append_gaas_audit(entries)

    # 2. MCP Guard audit log file entries (first-hand interception records)
    _append_mcp_guard_audit(entries)

    # 3. Governance router stats for current trust scores
    # (injected as synthetic entries so the dashboard shows agent state)

    # Sort by timestamp descending (newest first)
    entries.sort(key=lambda e: e.get("timestamp", 0), reverse=True)

    return entries[:max_entries]


def _append_gaas_audit(entries: list[dict[str, Any]]) -> None:
    """Append GaaS AuditLogService entries."""
    try:
        svc: AuditLogService = get_audit_service()
        for entry in svc.query(tenant_id="default", limit=200):
            entries.append({
                "id": entry.log_id,
                "timestamp": entry.timestamp,
                "type": "governance",
                "actor": entry.agent_id,
                "action": f"GaaS {entry.verdict} → {entry.action}",
                "details": f"Action: {entry.action}, Parameters: {json.dumps(entry.parameters)[:100]}",
                "severity": "ALLOW" if entry.verdict == "ALLOW" else "DENY" if entry.verdict == "DENY" else "WARN",
                "metadata": {
                    "source": "gaas",
                    "verdict": entry.verdict,
                    "hmac": entry.hmac_signature[:16],
                },
            })
    except Exception:
        pass  # GaaS audit service might not be initialized


def _append_mcp_guard_audit(entries: list[dict[str, Any]]) -> None:
    """Append MCP Guard audit log file entries."""
    if not MCP_GUARD_AUDIT_LOG.exists():
        return

    try:
        with open(MCP_GUARD_AUDIT_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    tool = record.get("tool", "Unknown")
                    label = TOOL_LABEL.get(tool, tool)

                    entries.append({
                        "id": record.get("id", f"mcp-{time.time()}"),
                        "timestamp": record.get("timestamp", time.time()),
                        "type": "governance",
                        "actor": record.get("agent_id", "unknown"),
                        "action": f"MCP {record.get('decision', 'unknown')} → {label}",
                        "details": record.get("reason", "")[:100],
                        "severity": "ALLOW" if record.get("decision") == "allow" else "DENY",
                        "metadata": {
                            "source": "mcp_guard",
                            "tool": tool,
                            "file_path": record.get("file_path", ""),
                            "decision": record.get("decision"),
                        },
                    })
                except (json.JSONDecodeError, KeyError):
                    continue
    except (OSError, PermissionError):
        pass


def get_audit_counts() -> dict[str, int]:
    """Get audit log counts by type."""
    entries = build_unified_audit_log(max_entries=500)
    counts: dict[str, int] = {}
    for e in entries:
        t = e.get("type", "other")
        counts[t] = counts.get(t, 0) + 1
    return counts


def get_governance_stats() -> dict[str, Any]:
    """Get comprehensive governance statistics."""
    entries = build_unified_audit_log(max_entries=500)

    all_verdicts = [e for e in entries if e.get("type") == "governance"]
    allow_count = sum(1 for e in all_verdicts if "ALLOW" in e.get("action", "").upper())
    deny_count = sum(1 for e in all_verdicts if "DENY" in e.get("action", "").upper())

    # Agent breakdown
    agents: dict[str, dict[str, int]] = {}
    for e in all_verdicts:
        agent = e.get("actor", "unknown")
        if agent not in agents:
            agents[agent] = {"allow": 0, "deny": 0, "total": 0}
        if "ALLOW" in e.get("action", "").upper():
            agents[agent]["allow"] += 1
        else:
            agents[agent]["deny"] += 1
        agents[agent]["total"] += 1

    # Source breakdown
    sources: dict[str, int] = {}
    for e in entries:
        src = e.get("metadata", {}).get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    # Trust scores for known agents
    trust_scores: dict[str, float] = {}
    try:
        ts = get_trust_service()
        for agent_id in ["trae-cn", "opencode", "cursor"]:
            score = ts.get_score("default", agent_id)
            if score is not None:
                trust_scores[agent_id] = score
    except Exception as exc:
        print(f"[governance_stats] trust score lookup failed: {exc}", file=sys.stderr)

    return {
        "total_entries": len(entries),
        "governance_decisions": {
            "allow": allow_count,
            "deny": deny_count,
            "total": len(all_verdicts),
        },
        "agents": agents,
        "sources": sources,
        "trust_scores": trust_scores,
    }


def get_hitl_pending() -> list[dict[str, Any]]:
    """Get pending HITL events from GaaS HITL service."""
    try:
        hs = get_hitl_service()
        events = hs.list_pending("default")
        return [
            {
                "event_id": e.event_id,
                "agent_id": e.agent_id,
                "action": e.action,
                "description": e.description,
                "tier": e.tier.value,
                "created_at": e.created_at,
                "expires_at": e.expires_at,
            }
            for e in events
        ]
    except Exception:
        return []


def inject_into_sidecar(app: Any) -> None:
    """Inject unified audit bridge into a sidecar FastAPI app.
    """
    import sidecar.server as sidecar_mod

    # Defensive check: _audit_logs must exist
    if not hasattr(sidecar_mod, "_audit_logs") or not isinstance(sidecar_mod._audit_logs, list):
        print("  ⚠️  sidecar.server._audit_logs not found, skipping audit bridge injection")
        return

    real_entries = build_unified_audit_log(max_entries=500)

    # Convert to the format expected by the existing mock endpoints
    mock_style: list[dict] = []
    for e in real_entries:
        action = e.get("action", "")
        verdict = e.get("metadata", {}).get("verdict") or e.get("metadata", {}).get("decision", "")
        severity = "ALLOW" if verdict and verdict.upper() in ("ALLOW", "allow") else "DENY"

        mock_style.append({
            "id": e.get("id", ""),
            "type": e.get("type", "governance"),
            "actor": e.get("actor", ""),
            "action": action,
            "reason": e.get("details", "")[:80],
            "severity": severity,
            "timestamp": e.get("timestamp", time.time()),
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.get("timestamp", 0))),
            "metadata": e.get("metadata", {}),
        })

    # If we have real data, replace the mock list
    if mock_style:
        sidecar_mod._audit_logs.clear()
        sidecar_mod._audit_logs.extend(mock_style)
        injected_count = len(mock_style)
    else:
        injected_count = 0

    # Inject governance summary endpoint
    @app.get("/api/v1/governance/summary")
    async def governance_summary():
        """Comprehensive governance summary across all IDE agents."""
        return get_governance_stats()

    # MCP Guard audit ingestion endpoint
    @app.post("/api/v1/audit/ingest")
    async def ingest_audit(body: dict):
        """Receive audit entries from MCP Guard or other sources.

        Does NOT re-write to GaaS AuditLogService — the GaaS endpoint
        already logged it. This only updates the in-memory _audit_logs
        for real-time Sidecar API display.
        """
        import uuid as _uuid
        source = body.get("source", "external")
        entries = body.get("entries", [body])

        saved = 0
        errors = 0
        for entry in entries:
            try:
                ts = entry.get("timestamp", time.time())
                log_id = str(_uuid.uuid4())
                verdict = entry.get("verdict", "DENY")
                agent_id = entry.get("agent_id", "unknown")
                action = entry.get("action", "unknown")

                sidecar_mod._audit_logs.append({
                    "id": log_id,
                    "type": "governance",
                    "actor": agent_id,
                    "action": f"{source.upper()} {verdict} → {action}",
                    "reason": entry.get("context", {}).get("reason", "")[:80],
                    "severity": "ALLOW" if verdict == "ALLOW" else "DENY",
                    "timestamp": ts,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
                    "metadata": {"source": source, "verdict": verdict},
                })
                saved += 1
            except Exception as exc:
                errors += 1
                print(f"[ingest] error for entry {entry.get('agent_id','?')}/{entry.get('action','?')}: {exc}", file=sys.stderr)

        return {"ingested": saved, "errors": errors, "source": source}

    print(f"  ✅ Unified audit bridge injected — {injected_count} real entries replace mock data")
    print(f"     Sources: GaaS AuditLogService + ~/.maref_mcp_guard_audit.log")
