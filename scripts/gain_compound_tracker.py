#!/usr/bin/env python3
"""增益复利追踪 (Phase Delta D4) — 独立脚本

追踪飞轮增益率的周度变化趋势，记录到 reports/gain_compound_history.jsonl
"""
import json, os
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path("/Volumes/1TB-M2/public/maref/reports")
GAIN_LOG = REPORTS_DIR / "gain_compound_history.jsonl"


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def main():
    conf = load_json(REPORTS_DIR / "confidence_audit.json")
    if not conf:
        print("无置信度数据，跳过高利追踪")
        return

    now = datetime.now(timezone.utc)
    current = conf.get("confidence_30d", 68)

    history = []
    if GAIN_LOG.exists():
        with open(GAIN_LOG) as f:
            for line in f:
                try:
                    history.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass

    prev = history[-1].get("confidence") if history else 68
    change = current - prev

    entry = {
        "timestamp": now.isoformat(),
        "week": now.strftime("%Y-W%W"),
        "confidence": current,
        "weekly_change": round(change, 2),
        "compound_rate": round(current / 68 - 1, 4),
        "total_weeks": len(history) + 1,
    }

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(GAIN_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print("增益复利追踪")
    print("=" * 40)
    print(f"当前置信度: {current}")
    print(f"周变化: {change:+.2f}")
    print(f"累计复利率: {entry['compound_rate']:+.4f}")
    print(f"追踪周数: {entry['total_weeks']}")

    if len(history) >= 3:
        recent = [h["confidence"] for h in history[-3:]] + [current]
        increasing = all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1))
        print(f"趋势: {'📈 上升' if increasing else '波动/下降'}")
        if increasing:
            print("✅ 飞轮复利效应确认")
        else:
            print("⚠️ 飞轮增益趋平，需检查数据源或疫苗精度")

    print(f"\n历史记录: {GAIN_LOG}")


if __name__ == "__main__":
    main()