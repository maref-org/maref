# Cookbook: Compliance Audit Trail

This guide covers enabling HMAC-signed audit logging, querying and verifying audit chain integrity, and exporting for compliance reporting (EU AI Act, SOC 2).

## Prerequisites

```bash
pip install maref
```

## Step 1: Enable HMAC-Signed Audit Logging

```python
from pathlib import Path
from maref.governance.audit import AuditLogger

# In-memory audit (no persistence)
memory_audit = AuditLogger()

# File-based audit with HMAC signing
file_audit = AuditLogger(
    log_path=Path("./audit/maref.jsonl"),
    hmac_key="my-secure-hmac-key-please-change-in-production",
)

# Or via environment variable (recommended for production)
import os
os.environ["MAREF_HMAC_SECRET_KEY"] = "production-hmac-key"
env_audit = AuditLogger(log_path=Path("./audit/maref.jsonl"))
# Automatically reads MAREF_HMAC_SECRET_KEY from environment

# Log some entries
for i in range(3):
    file_audit.log(
        event_type="governance_decision",
        actor="agent-42",
        action="state_transition",
        details=f"INIT -> OBSERVE (round {i})",
        metadata={"from_state": "INIT", "to_state": "OBSERVE", "round": i},
    )

print(f"Logged {file_audit.count()} entries with HMAC signatures")
```

## Step 2: Query Audit Logs

```python
# Read all entries
all_entries = file_audit.read_all(max_entries=100)
print(f"Total entries: {len(all_entries)}")

for entry in all_entries:
    print(f"  [{entry.id}] {entry.event_type}: {entry.action}")
    print(f"    HMAC: {entry.hmac_signature[:16]}...")
    print(f"    Chain: {entry.chain_hash[:16]}...")

# Read recent entries
recent = file_audit.read_recent(n=10)

# Filtered queries
filtered = file_audit.read_filtered(
    event_type="governance_decision",
    actor="agent-42",
    start_time=1718600000.0,
    end_time=1718700000.0,
    max_entries=50,
)
print(f"Filtered: {len(filtered)} entries")

# Convenience methods
decisions = file_audit.export_json(
    event_type="governance_decision",
    max_entries=10,
)
```

## Step 3: Verify Audit Chain Integrity

```python
# Complete integrity verification
result = file_audit.verify_integrity()
print(f"Integrity intact: {result['integrity_intact']}")
print(f"Total entries: {result['total_entries']}")
print(f"Signed entries: {result['signed_entries']}")
print(f"Valid signatures: {result['valid_signatures']}")
print(f"Tampered entries: {result['tampered_entries']}")

# Tamper detection example
if not result["integrity_intact"]:
    print(f"WARNING: {len(result['tampered_entries'])} entries tampered!")
    for entry_id in result["tampered_entries"]:
        print(f"  Tampered: {entry_id}")
```

## Step 4: MCP Governance Audit Log

The MCP governance pipeline also maintains HMAC-signed audit logs.

```python
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel

governance = MCPGovernance()

# Simulate tool calls
for i in range(5):
    governance.evaluate(
        tool_name="read_file",
        args={"path": f"/tmp/test_{i}.txt"},
        trust_level=MCPTrustLevel.SEMI_TRUSTED,
        agent_id="agent-42",
    )

# Get audit summary
summary = governance.get_audit_summary()
print(f"Total MCP calls: {summary['total_calls']}")
print(f"Allowed: {summary['allowed']}")
print(f"Circuit breaker state: {summary['circuit_breaker_state']}")

# Get full audit log
audit_log = governance.get_audit_log()
for entry in audit_log:
    print(f"  {entry.timestamp.isoformat()} | {entry.agent_id} | {entry.tool_name} | {entry.verdict}")

# Verify HMAC signatures across entire chain
violations = governance.verify_audit_integrity()
print(f"Integrity violations: {len(violations)}")
```

## Step 5: Export for Compliance

### JSON Export

```python
# Export all governance audit entries as JSON
json_data = file_audit.export_json(
    event_type="governance_decision",
    start_time=1718600000.0,
    end_time=1718700000.0,
    max_entries=1000,
)

# Write to file for compliance review
import json
with open("compliance-export.json", "w") as f:
    json.dump(json_data, f, indent=2, ensure_ascii=False)
```

### Syslog Export

```python
# RFC 5424 syslog format (SIEM integration)
syslog_output = file_audit.export_syslog(max_entries=100)
print(syslog_output)
# <118>1 2026-06-17T10:30:00Z maref MAREF - - [audit@32473 event="governance_decision" actor="agent-42" action="state_transition"] INIT -> OBSERVE
```

### MCP Audit Export

```python
# JSON format
mcp_json = governance.export_audit_log(format="json")

# Syslog format
mcp_syslog = governance.export_audit_log(format="syslog")
print(mcp_syslog[:500])
```

## Step 6: Compliance Dashboard (EU AI Act & SOC 2)

```python
"""compliance_report.py — Generate compliance report snapshot."""
import json
from datetime import datetime
from pathlib import Path
from maref.governance.audit import AuditLogger


def generate_compliance_report(
    audit_path: str = "./audit/maref.jsonl",
    output_path: str = "compliance-report.json",
    hmac_key: str | None = None,
) -> dict:
    audit = AuditLogger(
        log_path=Path(audit_path),
        hmac_key=hmac_key,
    )

    # Integrity check
    integrity = audit.verify_integrity()

    # Count by event type
    entries = audit.read_all(max_entries=None)
    event_counts: dict[str, int] = {}
    for entry in entries:
        event_counts[entry.event_type] = event_counts.get(entry.event_type, 0) + 1

    # Count by actor
    actor_counts: dict[str, int] = {}
    for entry in entries:
        actor_counts[entry.actor] = actor_counts.get(entry.actor, 0) + 1

    report = {
        "report_generated": datetime.utcnow().isoformat(),
        "report_type": "compliance_snapshot",
        "audit_statistics": {
            "total_entries": len(entries),
            "signed_entries": integrity["signed_entries"],
            "integrity_intact": integrity["integrity_intact"],
            "tampered_entries": len(integrity["tampered_entries"]),
            "by_event_type": event_counts,
            "by_actor": actor_counts,
        },
        "eu_ai_act_compliance": {
            "article_12_record_keeping": {
                "automated_logging": True,
                "hmac_signed": integrity["signed_entries"] > 0,
                "integrity_verified": integrity["integrity_intact"],
            },
            "article_14_human_oversight": {
                "hitl_enabled": True,
                "spot_check_rate": 0.05,
            },
        },
        "soc_2_compliance": {
            "cc6_1_logical_access": {
                "audit_trail_active": True,
                "hmac_signing_active": integrity["signed_entries"] > 0,
            },
            "cc7_2_monitoring": {
                "integrity_checks_passed": integrity["integrity_intact"],
                "anomaly_detection_active": True,
            },
        },
        "audit_sample": [e.to_dict() for e in entries[-5:]],
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report


if __name__ == "__main__":
    report = generate_compliance_report(
        audit_path="./audit/maref.jsonl",
        hmac_key="my-hmac-key",
    )
    print(f"Report generated: {report['audit_statistics']['total_entries']} entries")
    print(f"Integrity intact: {report['audit_statistics']['integrity_intact']}")
    print(f"EU AI Act Article 12 compliant: {report['eu_ai_act_compliance']['article_12_record_keeping']['hmac_signed']}")
```

## Step 7: Unified Audit Store (Cross-Layer)

```python
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id

store = UnifiedAuditStore(persist_path=Path("./audit/unified.jsonl"))

# Records from different layers
records = [
    UnifiedAuditRecord(
        record_id=make_record_id("governance", 1),
        timestamp=1718612345.0,
        layer="governance",
        round=1,
        event_type="state_transition",
        source_module="GovernanceStateMachine",
        target_module="EightTrigramsGovernance",
        decision="transition_to_observe",
        justification="Starting observation cycle",
        outcome="success",
    ),
    UnifiedAuditRecord(
        record_id=make_record_id("orchestration", 1),
        timestamp=1718612346.0,
        layer="orchestration",
        round=1,
        event_type="task_decomposed",
        source_module="TaskDecomposer",
        target_module="AgentDispatcher",
        decision="decompose_task",
        justification="Task decomposed into 3 subtasks",
        outcome="success",
    ),
]

for record in records:
    store.append(record)

# Query by layer
gov_records = store.query_by_layer("governance")
print(f"Governance records: {len(gov_records)}")

# Query by event type
task_records = store.query_by_event("task_decomposed")
print(f"Task records: {len(task_records)}")

# Full export
all_records = store.export_all()
print(f"Total unified records: {len(all_records)}")
```

## Step 8: Integration Test

```python
"""test_compliance_audit.py"""
from pathlib import Path
import tempfile
from maref.governance.audit import AuditLogger
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel


def test_hmac_audit_integrity():
    with tempfile.TemporaryDirectory() as tmp:
        audit_path = Path(tmp) / "audit.jsonl"
        audit = AuditLogger(
            log_path=audit_path,
            hmac_key="test-key",
        )

        # Log entries
        for i in range(5):
            audit.log(
                event_type="test_event",
                actor=f"agent-{i}",
                action="test_action",
                details=f"Test entry {i}",
            )

        # Verify integrity
        result = audit.verify_integrity()
        assert result["integrity_intact"]
        assert result["total_entries"] == 5
        assert result["signed_entries"] == 5

        # Tamper: manually modify a log entry
        with open(audit_path) as f:
            lines = f.readlines()
        import json
        data = json.loads(lines[2])
        data["details"] = "TAMPERED"
        lines[2] = json.dumps(data) + "\n"
        with open(audit_path, "w") as f:
            f.writelines(lines)

        # Re-verify — should detect tampering
        result2 = audit.verify_integrity()
        assert not result2["integrity_intact"]
        assert len(result2["tampered_entries"]) >= 1

        print("HMAC audit integrity test passed!")


def test_mcp_governance_audit_export():
    governance = MCPGovernance()

    for i in range(3):
        governance.evaluate(
            tool_name="read_file",
            args={"path": f"/tmp/test_{i}.txt"},
            trust_level=MCPTrustLevel.SEMI_TRUSTED,
            agent_id="test-agent",
        )

    # Export JSON
    json_export = governance.export_audit_log(format="json")
    assert "agent_id" in json_export
    assert "test-agent" in json_export

    # Export syslog
    syslog_export = governance.export_audit_log(format="syslog")
    assert "MAREF-MCP-GOV" in syslog_export

    # Verify integrity
    violations = governance.verify_audit_integrity()
    assert len(violations) == 0

    print("MCP governance audit export test passed!")
```
