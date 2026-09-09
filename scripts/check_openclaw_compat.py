#!/usr/bin/env python3
"""OpenClaw ↔ MAREF 兼容性检查 (Phase Alpha A9)

检查维度:
1. maref-governance 插件与 OpenClaw peerDep 版本兼容性
2. @maref-org/sdk 与 @maref/openclaw-plugin 版本对齐
3. TypeScript 编译目标与 Node.js 运行时兼容性
4. 插件 hook 接口签名完整性（静态分析）

返回值:
  0 — 兼容（compatible）
  1 — 有变更需关注（minor changes）
  2 — 不兼容（breaking change）
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
GOVERNANCE_PKG = REPO_ROOT / "maref-governance" / "package.json"
PLUGIN_PKG = REPO_ROOT / "integrations" / "openclaw-plugin" / "package.json"
SDK_PKG = REPO_ROOT / "sdk" / "typescript" / "package.json"
GOVERNANCE_SRC = REPO_ROOT / "maref-governance" / "src" / "index.ts"
PLUGIN_SRC = REPO_ROOT / "integrations" / "openclaw-plugin" / "src" / "index.ts"


def load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def check_openclaw_peer_dep() -> tuple[int, str]:
    pkg = load_json(GOVERNANCE_PKG)
    if not pkg:
        return 2, "maref-governance/package.json not found"
    peer = pkg.get("peerDependencies", {}).get("openclaw", "")
    if not peer:
        return 1, "openclaw peerDep not declared (optional?)"
    # 检查版本范围格式
    if not re.match(r">=\d{4}\.\d+\.\d+", peer):
        return 1, f"openclaw peerDep version format unusual: {peer}"
    return 0, f"openclaw peerDep: {peer}"


def check_sdk_plugin_alignment() -> tuple[int, str]:
    plugin = load_json(PLUGIN_PKG)
    sdk = load_json(SDK_PKG)
    if not plugin:
        return 2, "integrations/openclaw-plugin/package.json not found"
    if not sdk:
        return 2, "sdk/typescript/package.json not found"
    plugin_sdk = plugin.get("dependencies", {}).get("@maref-org/sdk", "")
    sdk_version = sdk.get("version", "")
    if not plugin_sdk:
        return 1, "@maref-org/sdk not in plugin dependencies"
    if plugin_sdk != f"^{sdk_version}":
        return 1, f"version mismatch: plugin expects {plugin_sdk}, sdk is {sdk_version}"
    return 0, f"sdk={sdk_version}, plugin expects {plugin_sdk} (aligned)"


def check_hook_signatures() -> tuple[int, str]:
    if not GOVERNANCE_SRC.exists():
        return 2, "maref-governance/src/index.ts not found"
    content = GOVERNANCE_SRC.read_text()
    required_hooks = [
        "before_tool_call",
        "session_start",
        "session_end",
        "llm_input",
        "llm_output",
    ]
    missing = []
    for hook in required_hooks:
        if hook not in content:
            missing.append(hook)
    if missing:
        return 1, f"missing hook implementations: {', '.join(missing)}"
    return 0, f"all {len(required_hooks)} required hooks present"


def check_node_compat() -> tuple[int, str]:
    governance = load_json(GOVERNANCE_PKG)
    plugin = load_json(PLUGIN_PKG)
    if not governance and not plugin:
        return 1, "no package.json found for node compat check"
    ts_version = None
    for pkg in [governance, plugin]:
        if pkg:
            ts = (pkg.get("devDependencies", {}).get("typescript", "") or
                  pkg.get("dependencies", {}).get("typescript", ""))
            if ts:
                ts_version = ts
                break
    if not ts_version:
        return 1, "typescript version not found"
    if ts_version.startswith("^5"):
        return 0, f"TypeScript {ts_version} compatible with Node 22"
    return 1, f"TypeScript {ts_version} may not be compatible with Node 22"


def main() -> int:
    quiet = "--quiet" in sys.argv
    force = "--force" in sys.argv

    checks = [
        ("OpenClaw peerDep", check_openclaw_peer_dep),
        ("SDK ↔ Plugin alignment", check_sdk_plugin_alignment),
        ("Hook signatures", check_hook_signatures),
        ("Node.js compat", check_node_compat),
    ]

    max_code = 0
    results = []

    for name, fn in checks:
        code, msg = fn()
        results.append((code, name, msg))
        max_code = max(max_code, code)

    if not quiet:
        print("MAREF ↔ OpenClaw Compatibility Check")
        print("=" * 50)
        for code, name, msg in results:
            status = {0: "PASS", 1: "WARN", 2: "FAIL"}[code]
            print(f"  [{status}] {name}: {msg}")
        print("=" * 50)
        verdict = {0: "COMPATIBLE", 1: "MINOR_CHANGES", 2: "BREAKING"}[max_code]
        print(f"  VERDICT: {verdict}")

    return max_code


if __name__ == "__main__":
    sys.exit(main())