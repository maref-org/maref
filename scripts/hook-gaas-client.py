#!/usr/bin/env python3
"""Hook→GaaS bridge client — calls local GaaS for git action governance.

Usage:
  hook-gaas-client.py push --remote-url <url> --remote-ref <ref>
  hook-gaas-client.py commit

Returns 0 if ALLOW, 1 if DENY. Exits 0 gracefully if GaaS unavailable.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEY_FILE = os.path.join(_PROJECT_ROOT, ".gaas_api_key")
_GaaS_URL = os.environ.get("GaaS_URL", "http://127.0.0.1:8080")
_TIMEOUT = int(os.environ.get("GaaS_TIMEOUT", "5"))


def _read_api_key() -> str | None:
    if not os.path.isfile(_KEY_FILE):
        return None
    try:
        with open(_KEY_FILE) as f:
            return f.read().strip()
    except OSError:
        return None


def _govern(action: str, agent_id: str, params: dict) -> dict | None:
    api_key = _read_api_key()
    if not api_key:
        return None

    payload = json.dumps({
        "tenant_id": "",
        "agent_id": agent_id,
        "action": action,
        "parameters": params,
        "context": {"session_id": "", "recursion_depth": 0, "trust_score": 80.0},
    }).encode()

    req = urllib.request.Request(
        f"{_GaaS_URL}/api/v1/gaas/govern",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"  ⚠ GaaS auth failed (invalid API key)", file=sys.stderr)
            return None
        body = e.read().decode()
        print(f"  ⚠ GaaS error ({e.code}): {body}", file=sys.stderr)
        return None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        print(f"  ⚠ GaaS unavailable ({e}). Skipping governance check.", file=sys.stderr)
        return None


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: hook-gaas-client.py <push|commit> [--remote-url <url>] [--remote-ref <ref>]", file=sys.stderr)
        return 0

    action = sys.argv[1]
    agent_id = f"git-hook@{os.uname().nodename}"

    params = {}
    if action == "push":
        for i, arg in enumerate(sys.argv[2:], start=2):
            if arg == "--remote-url" and i + 1 < len(sys.argv):
                params["remote_url"] = sys.argv[i + 1]
            elif arg == "--remote-ref" and i + 1 < len(sys.argv):
                params["remote_ref"] = sys.argv[i + 1]

    result = _govern(action, agent_id, params)

    if result is None:
        return 0

    verdict = result.get("verdict", "DENY")
    reason = result.get("reason", "")
    audit_id = result.get("audit_log_id", "")

    if verdict == "ALLOW":
        print(f"  ✅ GaaS: {action} allowed — {reason}")
        if audit_id:
            print(f"     audit: {audit_id}")
        return 0

    if verdict == "DENY":
        print(f"  ⛔ GaaS: {action} blocked — {reason}", file=sys.stderr)
        if audit_id:
            print(f"     audit: {audit_id}", file=sys.stderr)
        return 1

    print(f"  ⛔ GaaS: {action} requires approval — {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
