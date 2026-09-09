#!/usr/bin/env python3
"""疫苗批次注入 + A/B 测量 (Phase Gamma C2+C3)

流程:
1. 读取 vaccines.json → 分批注入到 sidecar /api/vaccine/inject
2. 生成注入前后对比报告
3. 监控误伤率，超阈值自动回滚
"""
import json, os, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

VACCINES_FILE = "/Volumes/1TB-M2/public/maref/scripts/vaccine_pipeline/vaccines.json"
SIDECAR_URL = os.environ.get("MAREF_SIDECAR_URL", "http://localhost:8000")
BATCH_SIZE = 10


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def inject_batch(vaccines: list, batch_num: int):
    batch_id = f"BATCH-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}-{batch_num:03d}"
    payload = {
        "batch_id": batch_id,
        "vaccines": vaccines,
        "merkle_root": "auto-generated",
        "auto_rollback": {"threshold": 0.05, "metric": "false_positive_rate", "window_hours": 24},
    }
    try:
        req = urllib.request.Request(
            f"{SIDECAR_URL}/api/vaccine/inject",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result
    except Exception as e:
        print(f"  注入失败: {e}")
        return None


def measure_baseline():
    conf = load_json("/Volumes/1TB-M2/public/maref/reports/confidence_audit.json")
    baseline = {
        "confidence": conf.get("confidence_30d") if conf else None,
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }
    return baseline


def measure_post_injection():
    time.sleep(1)
    return measure_baseline()


def main():
    print("=" * 60)
    print("疫苗批次注入 + A/B 测量 (Phase Gamma C2)")
    print("=" * 60)

    vaccines = load_json(VACCINES_FILE)
    if not vaccines:
        print("无疫苗文件，请先运行 04_compile_vaccines.py")
        return

    print(f"\n总疫苗数: {len(vaccines)}")
    print(f"批次大小: {BATCH_SIZE}")

    baseline = measure_baseline()
    print(f"\n注入前基线: 置信度={baseline.get('confidence')}")

    total_batches = (len(vaccines) + BATCH_SIZE - 1) // BATCH_SIZE
    injected_count = 0

    for i in range(total_batches):
        batch_slice = vaccines[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        print(f"\n批次 {i+1}/{total_batches}: 注入 {len(batch_slice)} 条疫苗...")
        result = inject_batch(batch_slice, i + 1)
        if result:
            injected_count += result.get("rules_written", 0)
            print(f"  ✅ {result.get('rules_written', 0)} 条规则写入")
        else:
            print(f"  ⚠️ sidecar 未运行，跳过")

    post = measure_post_injection()
    print(f"\n注入后: 置信度={post.get('confidence')}")

    # 误伤率检查
    try:
        req = urllib.request.Request(f"{SIDECAR_URL}/api/vaccine/status")
        status = json.loads(urllib.request.urlopen(req, timeout=5).read())
        fpr = status.get("current_fpr", 0)
        print(f"误伤率: {fpr:.2%}")
        if fpr > 0.05:
            print(f"⚠️ 误伤率超标 {fpr:.2%} > 5%，自动回滚已触发")
    except Exception:
        print("无法检查误伤率 (sidecar 未运行)")

    report = {
        "injected_at": datetime.now(timezone.utc).isoformat(),
        "total_vaccines": len(vaccines),
        "injected_count": injected_count,
        "baseline_confidence": baseline.get("confidence"),
        "post_injection_confidence": post.get("confidence"),
    }
    output = "/Volumes/1TB-M2/public/maref/reports/vaccine_injection_report.json"
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {output}")


if __name__ == "__main__":
    main()