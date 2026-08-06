---
sidebar_position: 5
title: Compliance Audit
description: HMAC-signed audit trail and compliance reporting
---

# Cookbook: Compliance Audit Trail

This guide covers enabling HMAC-signed audit logging, querying and verifying audit chain integrity, and exporting for compliance reporting (EU AI Act, SOC 2).

## Step 1: Enable HMAC-Signed Audit Logging

```python
from pathlib import Path
from maref.governance.audit import AuditLogger

file_audit = AuditLogger(
    log_path=Path("./audit/maref.jsonl"),
    hmac_key="my-secure-hmac-key",
)

for i in range(3):
    file_audit.log(
        event_type="governance_decision",
        actor="agent-42",
        action="state_transition",
        details=f"INIT -> OBSERVE (round {i})",
    )
```

## Step 2: Query Audit Logs

```python
all_entries = file_audit.read_all(max_entries=100)
recent = file_audit.read_recent(n=10)
filtered = file_audit.read_filtered(
    event_type="governance_decision",
    actor="agent-42",
)
```

## Step 3: Verify Audit Chain Integrity

```python
result = file_audit.verify_integrity()
print(f"Integrity intact: {result['integrity_intact']}")
print(f"Tampered entries: {result['tampered_entries']}")
```

## Step 4: Export for Compliance

```python
# JSON export
json_data = file_audit.export_json(
    event_type="governance_decision",
    max_entries=1000,
)

# Syslog export (RFC 5424)
syslog_output = file_audit.export_syslog(max_entries=100)
```

## Step 5: Compliance Dashboard

```python
def generate_compliance_report(audit_path: str = "./audit/maref.jsonl") -> dict:
    audit = AuditLogger(log_path=Path(audit_path))
    integrity = audit.verify_integrity()
    entries = audit.read_all(max_entries=None)

    return {
        "audit_statistics": {
            "total_entries": len(entries),
            "integrity_intact": integrity["integrity_intact"],
        },
        "eu_ai_act_compliance": {
            "article_12_record_keeping": {
                "hmac_signed": integrity["signed_entries"] > 0,
                "integrity_verified": integrity["integrity_intact"],
            },
        },
        "soc_2_compliance": {
            "cc6_1_logical_access": {
                "audit_trail_active": True,
            },
        },
    }
```

## Step 6: Unified Audit Store

```python
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore

store = UnifiedAuditStore(persist_path=Path("./audit/unified.jsonl"))
store.append(UnifiedAuditRecord(
    layer="governance",
    event_type="state_transition",
    source_module="GovernanceStateMachine",
    decision="transition_to_observe",
    outcome="success",
))
```

See the [full cookbook on GitHub](https://github.com/maref-org/maref/blob/main/docs/cookbook/compliance-audit.md) for the complete compliance report generator and integration tests.
