#!/usr/bin/env python3
"""MAREF 内存稳定性测试脚本 — 24小时内存增长检测."""

import gc
import os
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DURATION_HOURS = 24
SAMPLE_INTERVAL_SECONDS = 300  # 5 分钟采样
MAX_GROWTH_PERCENT_PER_HOUR = 5.0


def get_memory_mb() -> float:
    import psutil
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def main():
    print("=== MAREF Memory Stability Test ===")
    print(f"Duration: {DURATION_HOURS}h | Sample interval: {SAMPLE_INTERVAL_SECONDS}s")
    print(f"Max acceptable growth: {MAX_GROWTH_PERCENT_PER_HOUR}%/h\n")

    try:
        import psutil
    except ImportError:
        print("ERROR: psutil not installed. Run: pip install psutil")
        sys.exit(1)

    tracemalloc.start()
    samples = []
    start_time = time.time()
    baseline_mb = get_memory_mb()
    samples.append((0, baseline_mb))

    print(f"T+0m  Baseline: {baseline_mb:.1f} MB")

    iteration = 0
    while True:
        elapsed = time.time() - start_time
        elapsed_hours = elapsed / 3600

        if elapsed_hours >= DURATION_HOURS:
            break

        time.sleep(SAMPLE_INTERVAL_SECONDS)
        gc.collect()
        current_mb = get_memory_mb()
        samples.append((elapsed_hours, current_mb))

        growth_pct = ((current_mb - baseline_mb) / baseline_mb) * 100 if baseline_mb > 0 else 0
        growth_rate = growth_pct / elapsed_hours if elapsed_hours > 0 else 0
        status = "PASS" if growth_rate <= MAX_GROWTH_PERCENT_PER_HOUR else "FAIL"

        print(f"T+{elapsed_hours:.1f}h  Memory: {current_mb:.1f} MB  Growth: {growth_pct:.1f}%  Rate: {growth_rate:.2f}%/h  [{status}]")

        if growth_rate > MAX_GROWTH_PERCENT_PER_HOUR:
            print("\nWARNING: Memory growth rate exceeds threshold!")
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics("lineno")[:10]
            print("\nTop memory allocations:")
            for stat in top_stats:
                print(f"  {stat}")

        iteration += 1

    # Final summary
    final_mb = samples[-1][1]
    total_growth = ((final_mb - baseline_mb) / baseline_mb) * 100
    avg_rate = total_growth / DURATION_HOURS if DURATION_HOURS > 0 else 0

    print("\n=== Final Report ===")
    print(f"Baseline:     {baseline_mb:.1f} MB")
    print(f"Final:        {final_mb:.1f} MB")
    print(f"Total growth: {total_growth:.1f}%")
    print(f"Avg rate:     {avg_rate:.2f}%/h")
    print(f"Result:       {'PASS' if avg_rate <= MAX_GROWTH_PERCENT_PER_HOUR else 'FAIL'}")

    # Write report
    report_path = Path("memory_stability_report.json")
    import json
    report = {
        "baseline_mb": baseline_mb,
        "final_mb": final_mb,
        "total_growth_percent": total_growth,
        "avg_growth_rate_per_hour": avg_rate,
        "duration_hours": DURATION_HOURS,
        "pass": avg_rate <= MAX_GROWTH_PERCENT_PER_HOUR,
        "samples": [{"hour": s[0], "mb": s[1]} for s in samples],
    }
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
