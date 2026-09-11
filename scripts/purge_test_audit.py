#!/usr/bin/env python3
"""清理被测试/压力/混沌脚本污染的审计链（INC-2026-08-13-001 / G6-3）。

将 .governance/governance_audit.jsonl 中 details ∈ {bench, cli_observe, c*_r*}
的测试噪声记录归档到 archive/，保留真实治理事件重建干净链。

用法:
    python3 scripts/purge_test_audit.py           # dry-run
    python3 scripts/purge_test_audit.py --apply   # 执行归档
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / ".governance" / "governance_audit.jsonl"
ARCHIVE_DIR = REPO_ROOT / ".governance" / "archive" / "test-noise"

_TEST_REASON_RE = re.compile(
    r"^(bench|cli_observe|cli_observe_force|c\d+_r\d+)$",
    re.IGNORECASE,
)
# 额外的测试标签，仅当 actor=state_machine 时视为噪声
# 保守起见只匹配明确测试标签，不匹配真实安全告警/治理原因（alert-*/threat/emergency 等）
_TEST_TAG_RE = re.compile(
    r"(Fast-Screen FAIL|^test$|^setup$|^start$|Processing: Q\d+|Direct: Q\d+|"
    r"^latency test$|^t\d+$|^Cycle \d+$|orchestrator_initialize|"
    r"^analyze$|oscillation_fix_loop|^auto_init$|dual_threshold_primary)",
    re.IGNORECASE,
)


def _is_test_noise(rec: dict) -> bool:
    """判断一条审计记录是否为测试/压力噪声。"""
    # v0.54 G6：测试环境写入的记录 actor 带 :test 后缀
    if str(rec.get("actor", "")).endswith(":test"):
        return True
    reason = str(rec.get("details", ""))
    if _TEST_REASON_RE.match(reason):
        return True
    # 集中涌入的 state_machine 自转记录，带测试标签视为噪声
    return rec.get("actor") == "state_machine" and _TEST_TAG_RE.search(reason) is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="清理审计链测试噪声")
    parser.add_argument("--apply", action="store_true", help="执行归档（默认 dry-run）")
    args = parser.parse_args()

    if not AUDIT_PATH.exists():
        print(f"审计链不存在: {AUDIT_PATH}")
        return 1

    noise: list[str] = []
    clean: list[str] = []
    with open(AUDIT_PATH) as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if _is_test_noise(rec):
                noise.append(ln)
            else:
                clean.append(ln)

    print(f"总记录: {len(noise) + len(clean)} | 噪声: {len(noise)} | 保留: {len(clean)}")
    if not noise:
        print("无测试噪声，无需清理。")
        return 0

    if not args.apply:
        print(f"[dry-run] 将归档 {len(noise)} 条到 {ARCHIVE_DIR}（--apply 执行）")
        return 0

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    archive_file = ARCHIVE_DIR / f"governance_audit-test-noise-{ts}.jsonl"
    archive_file.write_text("\n".join(noise) + "\n")
    AUDIT_PATH.write_text("\n".join(clean) + ("\n" if clean else ""))
    print(f"✅ 已归档 {len(noise)} 条到 {archive_file}")
    print(f"✅ 干净审计链保留 {len(clean)} 条: {AUDIT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
