#!/usr/bin/env python3
"""飞轮调度器 (Phase Delta D2)

每周自动运行完整飞轮周期:
1. 数据采集 → 模式抽取 → 疫苗编译
2. 红皇后校验 → 合格疫苗注入
3. 自证报告生成 → 增益复利追踪
"""
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/Volumes/1TB-M2/public/maref")
SCRIPTS = REPO_ROOT / "scripts"
REPORTS = REPO_ROOT / "reports"


def run_script(name: str) -> bool:
    path = SCRIPTS / name
    if not path.exists():
        print(f"  ⚠️ {name} 不存在")
        return False
    result = subprocess.run([sys.executable, str(path)], capture_output=True, text=True)
    ok = result.returncode == 0
    print(f"  {'✅' if ok else '❌'} {name}")
    return ok


def main():
    print("=" * 60)
    print(f"飞轮调度器 (Phase Delta D2) — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    results = {}

    print("\n[1/5] 数据闭环")
    results["P-02"] = run_script("proposal_reconcile.py")
    results["P-06"] = run_script("confidence_realtime.py")
    results["P-09"] = run_script("gain_audit.py")

    print("\n[2/5] 疫苗管线")
    results["P-07-extract"] = run_script("vaccine_pipeline/01_extract_patterns.py")
    results["P-07-compile"] = run_script("vaccine_pipeline/04_compile_vaccines.py")

    print("\n[3/5] 红皇后校验")
    results["D1-red-queen"] = run_script("red_queen_validator.py")

    print("\n[4/5] 疫苗注入")
    results["C2-inject"] = run_script("vaccine_pipeline/05_inject_and_measure.py")

    print("\n[5/5] 自证报告 + 复利追踪")
    results["D3-cert"] = run_script("auto_cert_report.py")
    results["D4-gain"] = run_script("gain_compound_tracker.py")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"飞轮完成: {passed}/{total} 通过")

    report = {
        "flywheel_run_at": datetime.now(timezone.utc).isoformat(),
        "results": {k: "pass" if v else "fail" for k, v in results.items()},
        "pass_rate": f"{passed}/{total}",
    }
    output = REPORTS / f"flywheel-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.json"
    os.makedirs(REPORTS, exist_ok=True)
    with open(output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"飞行日志: {output}")


if __name__ == "__main__":
    main()