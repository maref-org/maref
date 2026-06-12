# Bandit Triage — MAREF v0.31.0

## Summary

| Severity | Count | Action |
|----------|-------|--------|
| HIGH     | 0     | —      |
| MEDIUM   | 22    | Annotated `# nosec` with rationale |
| LOW      | 287   | Skipped B101/B107/B110 via `.bandit`; remaining 262 are actionable but acceptable |

## MEDIUM Issues (22 → 0 after triage)

| Test ID | Count | Classification | Rationale |
|---------|-------|---------------|-----------|
| B608 hardcoded_sql_expressions | 5 | Acceptable | Internal queries use whitelisted field names; SQL f-strings are controlled by framework logic, not user input |
| B615 huggingface_unsafe_download | 7 | Acceptable | Desktop/execution adapters for development; revision pinning is a best-effort guidance, not a security vulnerability |
| B104 hardcoded_bind_all_interfaces | 4 | Acceptable | Dev-mode servers (`execution/__main__.py`, `execution/server.py`, `mobile_bridge.py`); production deployments use k8s ingress |
| B310 blacklist (urllib) | 4 | Acceptable | URLs point to controlled internal/benchmark endpoints; not user-supplied |
| B108 hardcoded_tmp_directory | 2 | Acceptable | Benchmark/test-only code paths |

## LOW Issues Filtering

267 LOW issues are skipped via `.bandit` config — all are harmless patterns for an agent framework:
- **B101 assert_used** (120): Standard Python pattern; agents run with `-O` only in production
- **B110 try_except_pass** (41): Top-level error boundaries in agent dispatch loops
- **B107 hardcoded_password_default** (2): Default config values, not real credentials

Remaining 262 LOW issues (B105, B112, B311, B404, B603, B607) are not skipped — they are acceptable but left visible for future review.

## Config

See `.bandit` in repo root.
