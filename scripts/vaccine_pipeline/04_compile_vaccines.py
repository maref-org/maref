#!/usr/bin/env python3
"""阶段4: 从模式编译疫苗规则"""
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from maref_config import vaccine_path

PATTERNS_FILE = str(vaccine_path("patterns.json"))


def _without_compiled_at(vaccines):
    """剔除易变字段，用于判断疫苗内容是否真的变了。"""
    return [
        {**v, "batch": {k: val for k, val in (v.get("batch") or {}).items() if k != "compiled_at"}}
        for v in vaccines
    ]


def _load_existing(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, list) else None


def compile_vaccines():
    if not os.path.exists(PATTERNS_FILE):
        print("模式文件不存在，请先运行 01_extract_patterns.py")
        return

    with open(PATTERNS_FILE) as f:
        patterns = json.load(f)

    vaccines = []
    for pattern in patterns:
        vaccine = {
            "vaccine_id": f"VAX-{len(vaccines)+1:04d}",
            "source_pattern": pattern['pattern_id'],
            "attack_class": pattern['attack_class'],
            "product": {
                "safetygate_rule": {
                    "type": "block_pattern",
                    "pattern": pattern['trigger'],
                    "action": "DENY",
                    "reason": f"疫苗阻断: {pattern['attack_class']}"
                }
            },
            "batch": {
                "compiled_at": datetime.now().isoformat(),
                "merkle_root": hashlib.sha256(json.dumps(pattern).encode()).hexdigest()
            },
            "status": "candidate"
        }
        vaccines.append(vaccine)

    print("=" * 60)
    print("疫苗编译报告")
    print("=" * 60)
    print(f"\n输入模式数: {len(patterns)}")
    print(f"编译疫苗数: {len(vaccines)}")

    for v in vaccines:
        print(f"\n  疫苗: {v['vaccine_id']}")
        print(f"  攻击类: {v['attack_class']}")
        print(f"  状态: {v['status']}")

    output_path = str(vaccine_path("vaccines.json"))
    existing = _load_existing(output_path)
    if existing is not None and _without_compiled_at(existing) == _without_compiled_at(vaccines):
        # 每日定时编译只改 compiled_at 会让工作区永久 dirty；内容没变就不写
        print("\n疫苗内容无变更，跳过写入（保留既有 compiled_at）")
        return vaccines

    with open(output_path, 'w') as f:
        json.dump(vaccines, f, indent=2)

    print(f"\n疫苗已保存: {output_path}")
    return vaccines

if __name__ == "__main__":
    compile_vaccines()
