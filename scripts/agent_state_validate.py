#!/usr/bin/env python3
"""
外围 Code Agent 状态一致性验证器

用法:
    python3 scripts/agent_state_validate.py <agent_name>

所有外围 Code Agent(Claude Code / Cursor / Opencode / Trae)
在每次会话启动时运行本脚本。如果 STATE.yaml version 大于
上次读取的 version，则输出过时警告和需要重新读取的字段列表。

返回码:
    0 — 状态一致
    1 — STATE.yaml 比 Agent 更新，须重新加载
    2 — STATE.yaml 不存在
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "STATE.yaml"
CACHE_DIR = REPO_ROOT / ".opencode" / "maref" / "cache"

FIELDS = [
    "current_release",
    "stage",
    "arxive.id",
    "aip_application.status",
    "d1_gate.gate_passed",
    "track_b.ci_status",
    "track_b.branch_protection",
    "trademark.application",
]


def get_state_version() -> int:
    if not STATE_PATH.exists():
        return -1
    content = STATE_PATH.read_text()
    m = re.search(r"^version:\s*(\d+)", content, re.M)
    return int(m.group(1)) if m else -1


def get_cached_version(agent: str) -> int:
    cache_file = CACHE_DIR / f"{agent}_state_version"
    if cache_file.exists():
        return int(cache_file.read_text().strip())
    return 0


def write_cached_version(agent: str, version: int):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{agent}_state_version"
    cache_file.write_text(str(version))


def main():
    agent = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    state_ver = get_state_version()
    if state_ver < 0:
        print(f"❌ STATE.yaml 不存在于 {STATE_PATH}")
        sys.exit(2)

    cached_ver = get_cached_version(agent)

    if state_ver > cached_ver:
        print(f"[{agent}] 🔔 STATE.yaml 已更新 (v{cached_ver} → v{state_ver})")
        print(f"[{agent}]     Agent 状态过时，请重新读取以下字段:")
        print(f"[{agent}]     ┌──────────────────────────────────┐")
        for field in FIELDS:
            print(f"[{agent}]     │  • {field}")
        print(f"[{agent}]     └──────────────────────────────────┘")
        write_cached_version(agent, state_ver)
        sys.exit(1)

    print(f"[{agent}] ✅ STATE.yaml v{state_ver} — 状态一致")
    write_cached_version(agent, state_ver)
    sys.exit(0)


if __name__ == "__main__":
    main()
