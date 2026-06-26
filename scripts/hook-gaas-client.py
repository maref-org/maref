#!/usr/bin/env python3
"""GaaS Hook Client — pre-push/pre-commit governance check via GaaS API.

Usage:
    python3 scripts/hook-gaas-client.py --action git.push --agent-id <id> --tenant-id <tenant>
    python3 scripts/hook-gaas-client.py --action git.commit --agent-id <id> --tenant-id <tenant>

Exits 0 if allowed, 1 if denied, 2 if HITL pending.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="GaaS governance hook client")
    parser.add_argument("--action", required=True, help="Action to check (e.g. git.push, git.commit)")
    parser.add_argument("--agent-id", default="hook-agent", help="Agent identifier")
    parser.add_argument("--tenant-id", default="default", help="Tenant identifier")
    parser.add_argument("--gaas-url", default=os.environ.get("GAAS_URL", "http://localhost:8080"),
                        help="GaaS API base URL")
    parser.add_argument("--api-key", default=os.environ.get("GAAS_API_KEY", ""),
                        help="GaaS API key")
    args = parser.parse_args()

    payload: dict[str, Any] = {
        "tenant_id": args.tenant_id,
        "agent_id": args.agent_id,
        "action": args.action,
        "parameters": {},
        "context": {
            "session_id": "",
            "recursion_depth": 0,
            "trust_score": 50.0,
        },
    }

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    req = Request(
        url=f"{args.gaas_url}/api/v1/gaas/govern",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
    except Exception as e:
        print(f"GaaS hook error: {e}", file=sys.stderr)
        sys.exit(1)

    verdict = result.get("verdict", "DENY")
    reason = result.get("reason", "No reason")

    if verdict == "ALLOW":
        print(f"GaaS: {args.action} allowed — {reason}")
        sys.exit(0)
    elif verdict == "ASK_USER":
        print(f"GaaS: {args.action} requires human approval — {reason}", file=sys.stderr)
        sys.exit(2)
    else:
        print(f"GaaS: {args.action} denied — {reason}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
