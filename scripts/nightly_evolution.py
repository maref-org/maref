#!/usr/bin/env python3
"""Track B 夜间进化流水线 — 红蓝对抗 → 混沌测试 → 数据 ingest 落盘（对齐 openclaw 版）。

设计（对齐补全分析 §4.2）:
    - MAREF 开源本地仓库（Track B）自建夜间流水线，复用自家引擎（red_blue_engine.py /
      immunity / tests/chaos），让 Track A/B 两侧各自产生对抗数据，可交叉比对净化。
    - 输出统一落到 .evolution_vault/（已 gitignore 隔离，绝密数据不入 OSS 发布）。

调度: launchd com.maref.nightly-evolution（Track B 侧，默认凌晨 02:30，避开 openclaw 侧 02:00）

链路:
    1. 红蓝对抗   — maref.redblue 5 阶段递增采样（red R1→R5 / blue B1→B5）
    2. 混沌测试   — pytest tests/chaos/ 选定场景（SIMULATE 默认，无真实故障注入）
    3. 数据落盘   — ingest redblue/chaos → .evolution_vault/rounds.db / .chaos-reports/

用法:
    python scripts/nightly_evolution.py                # 全链路
    python scripts/nightly_evolution.py --dry-run      # 只生成报告不写 DB（验证用）
    python scripts/nightly_evolution.py --rounds 20    # 红蓝每阶段轮数（默认 4 = 共 20 轮）
    python scripts/nightly_evolution.py --skip-chaos   # 跳过混沌测试
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from maref.redblue import (  # noqa: E402
    PHASE1_ATTACKS,
    PHASE2_ATTACKS,
    PHASE3_ATTACKS,
    PHASE4_ATTACKS,
    PHASE5_ATTACKS,
    BlueLevel,
    RedBlueEngine,
    RedLevel,
)

VAULT_DIR = REPO_ROOT / ".evolution_vault"
CHAOS_REPORT_DIR = REPO_ROOT / ".chaos-reports"
CHAOS_TEST_PATH = "tests/chaos/test_chaos_scenarios.py"
INGEST_SCRIPT = SCRIPTS_DIR / "evolution_ingest.py"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_redblue(rounds_per_phase: int = 4) -> dict:
    """红蓝对抗 5 阶段采样（红 R1→R5 / 蓝 B1→B5 递增），对齐 openclaw 版。"""
    engine = RedBlueEngine()
    phases = [
        (PHASE1_ATTACKS, RedLevel.R1, BlueLevel.B1),
        (PHASE2_ATTACKS, RedLevel.R2, BlueLevel.B2),
        (PHASE3_ATTACKS, RedLevel.R3, BlueLevel.B3),
        (PHASE4_ATTACKS, RedLevel.R4, BlueLevel.B4),
        (PHASE5_ATTACKS, RedLevel.R5, BlueLevel.B5),
    ]
    for pi, (attacks, red_level, blue_level) in enumerate(phases):
        # 轮转采样: 从本轮起始偏移开始循环取 rounds_per_phase 个攻击，
        # 避免顺序切片只覆盖数组前 N 个、其余攻击永不参与演练
        n_attack = len(attacks)
        offset = pi % max(n_attack, 1)
        for i in range(rounds_per_phase):
            attack = attacks[(offset + i) % n_attack]
            engine.run_round(
                round_id=f"RB{100 + pi * 100 + i}",
                phase=pi + 1,
                attack=attack,
                red_level=red_level,
                blue_level=blue_level,
            )
    results = engine.results() if callable(getattr(engine, "results", None)) else engine.results
    if not results:
        return {}

    def avg(attr: str) -> float:
        return round(sum(getattr(r, attr) for r in results) / len(results), 2)

    return {
        "rounds": len(results),
        "mean_score": round(sum(r.total_score for r in results) / len(results), 2),
        "detection": avg("detection_score"),
        "mitigation": avg("mitigation_score"),
        "recovery": avg("recovery_score"),
        "adaptation": avg("adaptation_score"),
        "passed": sum(1 for r in results if r.passed),
        "cb_triggers": sum(1 for r in results if r.cb_triggered),
    }


def run_chaos() -> dict:
    """运行混沌测试套件（SIMULATE 场景），返回报告 dict（对齐 openclaw chaos_report schema）。

    失败（超时/returncode!=0）返回 {"success": False, "error": ...}，绝不裸崩；
    已跑完的红蓝结果保留在 report 中。
    """
    cmd = [
        sys.executable, "-m", "pytest", CHAOS_TEST_PATH, "-q",
        "--no-header", "--tb=no", "--no-cov",
    ]
    t1 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            cwd=str(REPO_ROOT),  # 消除对调用方 cwd 的隐式依赖
        )
    except subprocess.TimeoutExpired as e:
        return {
            "test_suite": CHAOS_TEST_PATH,
            "timestamp": now_utc(),
            "passed": 0,
            "failed": 0,
            "total": 0,
            "success": False,
            "error": f"timeout 300s 已中止: {e}",
            "duration_ms": round((time.time() - t1) * 1000),
        }
    stdout = (proc.stdout or "") + (proc.stderr or "")
    passed = failed = 0
    # 解析 pytest 汇总行:「N passed, M failed in Xs」
    m = re.search(r"(\d+) passed", stdout)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", stdout)
    if m:
        failed = int(m.group(1))

    report = {
        "test_suite": CHAOS_TEST_PATH,
        "timestamp": now_utc(),
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "success": proc.returncode == 0,
        "duration_ms": round((time.time() - t1) * 1000),
    }
    # 失败诊断：带 stderr 尾部，避免 launchd 日志里只有 success=False 无从排查
    if proc.returncode != 0:
        report["error"] = (proc.stderr or "")[-800:]
        # 兜底：no tests ran / 收集失败（exit 5）解析会得到 0/0/0
        if passed == 0 and failed == 0:
            report["note"] = "pytest 未报告任何测试结果（可能收集失败或 no tests ran）"
    return report


def ingest(part: str, payload: dict) -> bool:
    """经 evolution_ingest.py 幂等落盘（--dry-run 时跳过）。

    返回 True 表示落盘成功（含幂等跳过）；失败返回 False 供 main 决定退出码。
    """
    proc = subprocess.run(
        [sys.executable, str(INGEST_SCRIPT), "add", "--part", part,
         "--json", json.dumps(payload, ensure_ascii=False)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"  [ingest:{part}] 失败: {(proc.stderr or '')[-500:]}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Track B 夜间进化流水线")
    parser.add_argument("--rounds", type=int, default=4, help="红蓝每阶段轮数（5 阶段）")
    parser.add_argument("--dry-run", action="store_true", help="完整跑但跳过 DB/文件落盘（验证用）")
    parser.add_argument("--skip-chaos", action="store_true")
    args = parser.parse_args()

    report = {"generated_at": now_utc()}
    t0 = time.time()

    print("== 1/2 红蓝对抗 ==")
    rb = run_redblue(args.rounds)
    report["redblue"] = rb

    chaos = {} if args.skip_chaos else run_chaos()
    report["chaos"] = chaos
    print(f"  混沌: {chaos.get('success') if chaos else 'skipped'}")

    ingest_ok = True
    if not args.dry_run:
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        if rb:
            ingest_ok &= ingest("redblue", {"run": rb})
        if chaos:
            ingest_ok &= ingest("chaos", {"run": chaos})
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        CHAOS_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (CHAOS_REPORT_DIR / f"nightly-run-{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print("  [dry-run] 完成全链路但未写 DB / 未落盘报告文件")

    print(f"总耗时: {time.time() - t0:.1f}s")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 落盘失败必须反映到退出码，避免 launchd 下 false-green
    if not args.dry_run and not ingest_ok:
        print("  ⚠️ 存在 ingest 落盘失败，进程以非零码退出", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
