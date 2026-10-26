#!/usr/bin/env bash
# Configure or verify main branch protection from configs/release-gate.yaml.
#
#   bash scripts/configure_branch_protection.sh --check   # default
#   bash scripts/configure_branch_protection.sh --apply
#
# Requires: gh authenticated with admin access (repo Administration: read/write
# for fine-grained tokens), python3, PyYAML.
#
# Exit codes: 0 = matches, 1 = drift / missing protection, 2 = tooling error.
set -euo pipefail

MODE="${1:---check}"
case "$MODE" in
  --check|--apply) ;;
  *) echo "usage: $0 [--check|--apply]" >&2; exit 2 ;;
esac

CONFIG="${RELEASE_GATE_CONFIG:-configs/release-gate.yaml}"
if [ ! -f "$CONFIG" ]; then
  echo "ERROR: config not found: $CONFIG" >&2
  exit 2
fi

TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$TOKEN" ]; then
  echo "ERROR: GH_TOKEN or GITHUB_TOKEN must be set (admin access required)" >&2
  exit 2
fi

if ! python3 -c "import yaml" 2>/dev/null; then
  echo "ERROR: PyYAML is required (pip install pyyaml)" >&2
  exit 2
fi

export MODE CONFIG TOKEN
export RELEASE_GATE_REPO="${RELEASE_GATE_REPO:-}"
export RELEASE_GATE_BRANCH="${RELEASE_GATE_BRANCH:-}"

python3 - <<'PY'
import json
import os
import subprocess
import sys

import yaml

mode = os.environ["MODE"]
config_path = os.environ["CONFIG"]
token = os.environ["TOKEN"]

with open(config_path) as fh:
    cfg = yaml.safe_load(fh) or {}

repo = os.environ.get("RELEASE_GATE_REPO") or cfg.get("repository")
branch = os.environ.get("RELEASE_GATE_BRANCH") or cfg.get("branch")
if not repo or not branch:
    sys.exit("ERROR: repository/branch missing from config")

protection = cfg.get("protection") or {}
required = list(cfg.get("required_checks") or []) + list(cfg.get("required_pr_checks") or [])
if not required:
    sys.exit("ERROR: required_checks must not be empty")

expect = {
    "contexts": set(required),
    "strict": bool(protection.get("strict_status_checks", True)),
    "enforce_admins": bool(protection.get("enforce_admins", True)),
    "reviews": int(protection.get("required_approving_review_count", 1)),
    "dismiss_stale": bool(protection.get("dismiss_stale_reviews", True)),
    "conversation": bool(protection.get("require_conversation_resolution", True)),
    "force_push": bool(protection.get("allow_force_pushes", False)),
    "deletions": bool(protection.get("allow_deletions", False)),
}


def api(method, path, body=None):
    env = dict(os.environ, GH_TOKEN=token)
    cmd = ["gh", "api", "--method", method, path]
    payload = None
    if body is not None:
        cmd += ["--input", "-"]
        payload = json.dumps(body)
    proc = subprocess.run(cmd, input=payload, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    if not proc.stdout.strip():
        return {}, None
    return json.loads(proc.stdout), None


def fetch():
    return api("GET", f"repos/{repo}/branches/{branch}/protection")


def actual_contexts(data):
    rsc = data.get("required_status_checks") or {}
    contexts = set(rsc.get("contexts") or [])
    for item in rsc.get("checks") or []:
        if item.get("context"):
            contexts.add(item["context"])
    return contexts


def diff(data):
    problems = []
    got = actual_contexts(data)
    missing = sorted(expect["contexts"] - got)
    extra = sorted(got - expect["contexts"])
    if missing:
        problems.append(f"missing contexts: {', '.join(missing)}")
    if extra:
        problems.append(f"unexpected contexts: {', '.join(extra)}")

    rsc = data.get("required_status_checks") or {}
    if bool(rsc.get("strict")) != expect["strict"]:
        problems.append(f"strict_status_checks: expected {expect['strict']}, got {rsc.get('strict')}")

    if bool((data.get("enforce_admins") or {}).get("enabled")) != expect["enforce_admins"]:
        problems.append(f"enforce_admins: expected {expect['enforce_admins']}")

    reviews = data.get("required_pull_request_reviews")
    if reviews is None:
        problems.append("required_pull_request_reviews: not enabled")
    else:
        if int(reviews.get("required_approving_review_count") or 0) != expect["reviews"]:
            problems.append(
                "required_approving_review_count: expected "
                f"{expect['reviews']}, got {reviews.get('required_approving_review_count')}"
            )
        if bool(reviews.get("dismiss_stale_reviews")) != expect["dismiss_stale"]:
            problems.append(f"dismiss_stale_reviews: expected {expect['dismiss_stale']}")

    if bool((data.get("required_conversation_resolution") or {}).get("enabled")) != expect["conversation"]:
        problems.append(f"required_conversation_resolution: expected {expect['conversation']}")

    if bool((data.get("allow_force_pushes") or {}).get("enabled")) != expect["force_push"]:
        problems.append(f"allow_force_pushes: expected {expect['force_push']}")

    if bool((data.get("allow_deletions") or {}).get("enabled")) != expect["deletions"]:
        problems.append(f"allow_deletions: expected {expect['deletions']}")

    return problems


def check(prefix="check"):
    data, err = fetch()
    if data is None:
        if "404" in err:
            print(f"{prefix}: FAIL - branch protection is not configured for {repo}@{branch}")
            return 1
        print(f"{prefix}: ERROR - {err}")
        return 2
    problems = diff(data)
    if problems:
        print(f"{prefix}: FAIL - {len(problems)} drift item(s) on {repo}@{branch}")
        for item in problems:
            print(f"  - {item}")
        return 1
    print(f"{prefix}: OK - {repo}@{branch} matches {config_path} ({len(expect['contexts'])} contexts)")
    return 0


if mode == "--check":
    sys.exit(check())

payload = {
    "required_status_checks": {
        "strict": expect["strict"],
        "contexts": sorted(expect["contexts"]),
    },
    "enforce_admins": expect["enforce_admins"],
    "required_pull_request_reviews": {
        "dismiss_stale_reviews": expect["dismiss_stale"],
        "require_code_owner_reviews": False,
        "required_approving_review_count": expect["reviews"],
    },
    "restrictions": None,
    "required_linear_history": False,
    "allow_force_pushes": expect["force_push"],
    "allow_deletions": expect["deletions"],
    "block_creations": False,
    "required_conversation_resolution": expect["conversation"],
    "lock_branch": False,
}

data, err = api("PUT", f"repos/{repo}/branches/{branch}/protection", payload)
if data is None:
    print(f"apply: ERROR - {err}")
    sys.exit(2)
print(f"apply: submitted {len(expect['contexts'])} contexts to {repo}@{branch}")
sys.exit(check("verify"))
PY
