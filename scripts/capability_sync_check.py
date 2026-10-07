#!/usr/bin/env python3
"""双仓能力同步校验（Phase 2.6）。

对比 openclaw 与 public/maref 已抽出版原语的文件 sha256，
检测 drift（私有侧改动未同步到开源），告警并阻断 CI。

单一事实源: capability_manifest.json（记录已抽出版原语的文件映射）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT_OPENCLAW = Path(os.environ.get("OPENCLAW_ROOT") or "/Volumes/1TB-M2/openclaw")
ROOT_PUBLIC = Path(os.environ.get("PUBLIC_MAREF_ROOT") or "/Volumes/1TB-M2/public/maref")
MANIFEST = ROOT_OPENCLAW / "scripts" / "capability_manifest.json"


DEFAULT_MANIFEST = {
    "version": 1,
    "mappings": [
        # Phase 2.1
        {"openclaw": "scripts/failure_event_bus.py", "public": "src/maref/governance/failure_event_bus.py", "capability": "failure_event_bus"},
        {"openclaw": "scripts/failure_attribution.py", "public": "src/maref/governance/failure_attribution.py", "capability": "failure_attribution"},
        {"openclaw": "scripts/stagnation_watcher.py", "public": "src/maref/infra/stagnation_watcher.py", "capability": "stagnation_detection"},
        {"openclaw": "scripts/healing_actions.py", "public": "src/maref/recursive/healing_actions.py", "capability": "healing_actions"},
        # Phase 2.2
        {"openclaw": "scripts/reflexion_bridge.py", "public": "src/maref/recursive/reflexion_bridge.py", "capability": "reflexion_bridge"},
        # Phase 2.5 (待 D1c 推送)
        # {"openclaw": "scripts/healing_actions.py", "public": "src/maref/governance/healing_strategy.py", "capability": "healing_strategy_routing"},
        # {"openclaw": "scripts/reflexion_bridge.py", "public": "src/maref/recursive/experience_pool_writeback.py", "capability": "experience_pool_writeback"},
        # {"openclaw": "src/maref/recursive/experience_pool.py", "public": "src/maref/recursive/experience_pool.py", "capability": "experience_pool"},
        # {"openclaw": "src/maref/governance/circuit_breaker_v2/retry_policy.py", "public": "src/maref/governance/retry_policy.py", "capability": "retry_policy"},
        # {"openclaw": "src/maref/recursive/failure_classifier.py", "public": "src/maref/governance/failure_classifier.py", "capability": "failure_classifier_interface"},
    ],
    "note": "待 D1c 推送的条目标注在注释中，manifest 仅跟踪已推送项"
}


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text())
        except json.JSONDecodeError:
            pass
    return DEFAULT_MANIFEST


def save_manifest(m: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2))


def check_sync(manifest: dict, fix: bool = False) -> dict:
    """对比两仓文件 sha，返回 drift 列表。"""
    drifts = []
    missing_public = []
    missing_openclaw = []

    for mapping in manifest.get("mappings", []):
        oc_path = ROOT_OPENCLAW / mapping["openclaw"]
        pub_path = ROOT_PUBLIC / mapping["public"]
        cap = mapping.get("capability", "unknown")

        oc_sha = sha256_file(oc_path)
        pub_sha = sha256_file(pub_path)

        if oc_sha is None:
            missing_openclaw.append({"capability": cap, "openclaw": str(oc_path)})
            continue
        if pub_sha is None:
            missing_public.append({"capability": cap, "public": str(pub_path)})
            continue

        if oc_sha != pub_sha:
            drifts.append({
                "capability": cap,
                "openclaw": str(oc_path),
                "public": str(pub_path),
                "openclaw_sha": oc_sha[:16],
                "public_sha": pub_sha[:16],
            })

    result = {
        "ok": len(drifts) == 0 and len(missing_public) == 0 and len(missing_openclaw) == 0,
        "drifts": drifts,
        "missing_public": missing_public,
        "missing_openclaw": missing_openclaw,
        "checked": len(manifest.get("mappings", [])),
    }

    if fix and drifts:
        # fix 模式：复制 openclaw -> public（需人工确认，这里只演示）
        for d in drifts:
            src = Path(d["openclaw"])
            dst = Path(d["public"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
        result["fixed"] = True

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="双仓能力同步校验（Phase 2.6）")
    ap.add_argument("--fix", action="store_true", help="自动修复（复制 openclaw -> public）")
    ap.add_argument("--init", action="store_true", help="初始化 manifest（从默认模板）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.init:
        save_manifest(DEFAULT_MANIFEST)
        print(f"Manifest 初始化: {MANIFEST}")
        return 0

    manifest = load_manifest()
    res = check_sync(manifest, fix=args.fix)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"检查 {res['checked']} 项能力映射")
        if res["ok"]:
            print("✅ 同步一致")
        else:
            print("❌ 发现 drift:")
            for d in res["drifts"]:
                print(f"  - {d['capability']}: openclaw={d['openclaw_sha']} vs public={d['public_sha']}")
            for m in res["missing_public"]:
                print(f"  - 缺失 public: {m['capability']} -> {m['public']}")
            for m in res["missing_openclaw"]:
                print(f"  - 缺失 openclaw: {m['capability']} -> {m['openclaw']}")

    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())