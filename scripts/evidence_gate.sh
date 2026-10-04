#!/usr/bin/env bash
# 治理证据门禁 — 全绿才退出 0（方案 docs/plans/2026-10-03-governance-evidence-completion.md §6）
set -uo pipefail
fail=0
chk(){ printf -- "- %s ... " "$1"; if bash -c "$2"; then echo OK; else echo FAIL; fail=1; fi; }

# 保证相对路径 (scripts/ reports/) 在 repo cwd 下解析
cd "$(dirname "$0")/.." || exit 1

# runtime 兜底（env → 配置 → repo）
RT="${MAREF_RUNTIME_DIR:-$(python3 -c 'from scripts.maref_config import RUNTIME_DIR;print(RUNTIME_DIR)' 2>/dev/null || pwd)}"

# 1 遥测新鲜 (<26h) — 生产 PROBE_DB（运行时库，env→runtime_dir.json→repo 三级解析）
chk "probe fresh" 'python3 -c "import sqlite3,time,sys;sys.path.insert(0,\"scripts\");from maref_config import PROBE_DB;v=sqlite3.connect(str(PROBE_DB)).execute(\"select max(timestamp) from probe_readings\").fetchone()[0];assert time.time()-float(v)<93600"'
# 2 sidecar 健康
chk "sidecar healthy" 'curl -sf -m3 http://127.0.0.1:8931/api/health | grep -q healthy'
# 3 hooks 链新鲜（先跑盘点，再断言无 STALE）
chk "hooks chain fresh" 'python3 scripts/audit_health_check.py >/dev/null && ! grep -q "hooks_agent: STALE" reports/audit_health_check.json'
# 4 主链可验证
chk "chain verify" "python3 scripts/verify_audit_chain.py --audit-file '$RT/governance_audit.jsonl'"
# 5 per-agent KPI 非零
chk "kpi>0" 'python3 -c "import json;d=json.load(open(\"reports/coding_agents_status.json\"));assert d[\"global_kpi\"][\"tool_calls_total\"]>0"'
# 6 覆盖对账
chk "coverage" 'python3 -c "import json;assert json.load(open(\"reports/agent_coverage_report.json\"))[\"gaps\"]==[]"'
# 7 证据报告产出
chk "evidence report" 'test -s reports/governance_evidence_report.json'

echo "evidence_gate: $([ $fail -eq 0 ] && echo PASS || echo FAIL)"
exit $fail
