#!/usr/bin/env python3
"""提案对账推送 (Phase Beta B5) — P-02 对账结果 → sidecar /api/proposal/ingest"""
import json, os, urllib.request
from collections import Counter
from datetime import datetime, timezone

AUDIT_LOG = "/Volumes/1TB-M2/public/maref/governance_audit_v2.jsonl"
RECURSIVE_LOG = "/Volumes/1TB-M2/public/maref/recursive_governance_audit_v2.jsonl"
SIDECAR_URL = os.environ.get("MAREF_SIDECAR_URL", "http://localhost:8000")


def load_entries(path):
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass
    return entries


def push_proposals():
    audit = load_entries(AUDIT_LOG)
    recursive = load_entries(RECURSIVE_LOG)
    decisions = [e for e in audit + recursive if e.get("event_type") == "governance_decision"]

    pushed = 0
    for entry in decisions:
        payload = {
            "proposal_id": entry.get("id", f"recon-{datetime.now(timezone.utc).timestamp()}"),
            "source": "maref-reconcile",
            "action": entry.get("action", "unknown"),
            "agent": entry.get("actor", "unknown"),
            "risk_level": entry.get("risk_level", "unknown"),
            "domain_weight": 1,
            "verdict": entry.get("verdict", "unknown"),
            "details": str(entry.get("details", ""))[:200],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            req = urllib.request.Request(
                f"{SIDECAR_URL}/api/proposal/ingest",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            pushed += 1
        except Exception:
            break

    print(f"提案对账推送: {pushed}/{len(decisions)} 条同步到 sidecar")


def main():
    verdicts = Counter()
    audit = load_entries(AUDIT_LOG)
    for e in audit:
        verdicts[e.get("verdict", "unknown")] += 1

    print("提案对账推送")
    print("=" * 40)
    print(f"审计条目: {len(audit)}")
    print(f"裁决分布: allow={verdicts.get('allow',0)}, deny={verdicts.get('deny',0)}, flag={verdicts.get('flag',0)}, unknown={verdicts.get('unknown',0)}")
    push_proposals()


if __name__ == "__main__":
    main()