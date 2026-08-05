#!/usr/bin/env python3
"""
PERCV Security Baseline Scanner — Agent 安全基线扫描器 PoC

5 维度安全检测:
  1. Prompt Injection — 提示注入防护检测
  2. Permission Abuse — 权限滥用检查
  3. Data Leakage — 数据泄露风险
  4. Behavior Drift — 行为漂移检测
  5. Identity Spoofing — 身份欺骗检测

用法:
    python3 scripts/security_baseline_scanner.py check <agent_config>
    python3 scripts/security_baseline_scanner.py report <results_file>
    python3 scripts/security_baseline_scanner.py list-checks
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] PERCV: %(message)s")
logger = logging.getLogger("percv_scanner")

# ── 数据模型 ────────────────────────────────────────────────

@dataclass
class SecurityCheckResult:
    check_id: str
    name: str
    category: str  # protect | evaluate | respond | contain | verify
    severity: str  # critical | high | medium | low
    status: str    # pass | fail | warn | skip
    detail: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

# ── PERCV 安全框架核心 ─────────────────────────────────────

PERCV_CHECKS = [
    # P — Protect
    SecurityCheckResult("P-01", "提示注入边界检测", "protect", "critical", "skip",
                        "检查 Agent 是否有输入净化层和指令边界检测机制",
                        "实现输入净化层，使用指令边界标记 '<|im_start|>' 隔离用户输入"),
    SecurityCheckResult("P-02", "最小权限原则", "protect", "high", "skip",
                        "检查 Agent 权限是否遵循最小必要原则",
                        "审计 Agent 权限声明，移除与任务无关的权限"),
    SecurityCheckResult("P-03", "数据访问控制", "protect", "high", "skip",
                        "检查 Agent 是否有数据访问边界控制",
                        "实施基于角色的数据访问控制 (RBAC)"),

    # E — Evaluate
    SecurityCheckResult("E-01", "行为基线检测", "evaluate", "medium", "skip",
                        "建立 Agent 正常行为基线，检测偏离",
                        "收集 7 天运行数据建立基线，设 ±2σ 告警阈值"),
    SecurityCheckResult("E-02", "安全配置审计", "evaluate", "high", "skip",
                        "检查 Agent 安全配置是否符合最佳实践",
                        "对照 OWASP Agentic Top 10 逐项审计"),

    # R — Respond
    SecurityCheckResult("R-01", "安全事件响应", "respond", "critical", "skip",
                        "检查是否有安全事件响应流程",
                        "制定安全事件响应计划，包含：检测→分析→遏制→恢复→复盘"),
    SecurityCheckResult("R-02", "自动回滚机制", "respond", "medium", "skip",
                        "检测异常行为时是否有自动回滚能力",
                        "实现自动回滚触发器，保存前 N 个稳定状态"),

    # C — Contain
    SecurityCheckResult("C-01", "攻击影响隔离", "contain", "high", "skip",
                        "单个 Agent 被攻破时能否隔离影响范围",
                        "实施 Agent 沙箱化，限制横向移动能力"),
    SecurityCheckResult("C-02", "权限即时回收", "contain", "medium", "skip",
                        "检测到异常时能否即时回收 Agent 权限",
                        "实现动态权限回收机制，支持手动和自动触发"),

    # V — Verify
    SecurityCheckResult("V-01", "安全措施有效性验证", "verify", "high", "skip",
                        "安全措施是否真正有效，而非形同虚设",
                        "定期进行红蓝对抗演练，验证安全防线"),
    SecurityCheckResult("V-02", "第三方依赖安全", "verify", "medium", "skip",
                        "Agent 的第三方依赖是否存在已知漏洞",
                        "集成 Snyk/Dependabot，自动检测依赖安全"),

    # 快速检查清单 (Quick Checklist)
    SecurityCheckResult("Q-01", "Agent 数字身份", "protect", "high", "skip",
                        "Agent 是否有唯一可验证的数字身份",
                        "为每个 Agent 分配公私钥对，操作签名验证"),
    SecurityCheckResult("Q-02", "审计日志完整性", "evaluate", "critical", "skip",
                        "所有 Agent 操作是否都有不可篡改的审计日志",
                        "集成 Runtime Audit Log，日志写入前签名"),
    SecurityCheckResult("Q-03", "漂移检测运行中", "evaluate", "medium", "skip",
                        "Agent 行为漂移检测是否持续运行",
                        "使用 RSI 收敛检测，配置漂移阈值告警"),
    SecurityCheckResult("Q-04", "数据泄露防护", "protect", "critical", "skip",
                        "是否有数据泄露防护措施",
                        "实施敏感数据脱敏 + 输出过滤 + 日志审查"),
]


def build_config() -> dict:
    """返回 PERCV 安全框架配置骨架"""
    return {
        "framework": "PERCV",
        "version": "1.0.0",
        "principles": {
            "protect": "保护数据和系统边界",
            "evaluate": "持续评估 Agent 行为",
            "respond": "快速响应安全事件",
            "contain": "限制攻击影响范围",
            "verify": "验证安全措施有效性",
        },
        "checks": [c.to_dict() for c in PERCV_CHECKS],
    }


def initialize_config(output: str = "percv_config.json") -> str:
    """生成 PERCV 配置文件"""
    config = build_config()
    path = output
    with open(path, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    logger.info("✅ PERCV 配置已生成: %s (%d 项检查)", path, len(PERCV_CHECKS))
    return path


def run_scan(config_file: str | None = None) -> dict:
    """运行安全基线扫描"""
    logger.info("🔍 PERCV 安全基线扫描启动...")

    checks = PERCV_CHECKS[:]  # Use all checks regardless of config

    results = []
    passed = 0
    failed = 0
    warned = 0

    for check in checks:
        # Mark all as "pending" — real integration would run actual checks
        results.append({
            "check_id": check.check_id,
            "name": check.name,
            "category": check.category,
            "severity": check.severity,
            "status": "pending",
            "detail": check.detail,
            "recommendation": check.recommendation,
        })

    report: dict[str, Any] = {
        "scanner": "PERCV Security Baseline Scanner",
        "version": "1.0.0",
        "scan_id": f"percv-scan-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "pending": len(results),
            "score": 0.0,
        },
        "checks": results,
        "framework": "PERCV",
    }

    # 计算安全评分
    if results:
        severity_weights = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.3}
        total_weight = sum(severity_weights.get(c["severity"], 0.5) for c in results)
        pending_weight = sum(severity_weights.get(c["severity"], 0.5)
                            for c in results if c["status"] == "pending")
        report["summary"]["score"] = round(
            (1 - pending_weight / max(total_weight, 1)) * 100, 1
        ) if total_weight > 0 else 0.0

    logger.info("✅ 扫描完成: %d 项检查, 安全评分: %.1f/100",
                report["summary"]["total"], report["summary"]["score"])
    return report


def print_report(report: dict):
    """打印人类可读的安全报告"""
    print(f"\n{'='*60}")
    print("  PERCV 安全基线扫描报告")
    print(f"  ID: {report['scan_id']}")
    print(f"{'='*60}")
    print(f"  框架: {report['framework']}")
    print(f"  时间: {report['scanned_at'][:19]}")
    print(f"  评分: {report['summary']['score']}/100")
    print(f"  总检查: {report['summary']['total']}")
    print(f"  ✅ 通过: {report['summary']['passed']}")
    print(f"  ❌ 失败: {report['summary']['failed']}")
    print(f"  ⚠️  警告: {report['summary']['warned']}")
    print(f"  ⏳ 待定: {report['summary']['pending']}")

    for check in report["checks"]:
        icon = {"pass": "✅", "fail": "❌", "warn": "⚠️", "pending": "⏳", "skip": "⬜"}
        status_icon = icon.get(check["status"], "❓")
        sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        sev = sev_icon.get(check["severity"], "⚪")
        print(f"\n  {status_icon} {sev} [{check['category']}] {check['check_id']}: {check['name']}")
        print(f"     {check['detail'][:80]}")
        print(f"     → {check['recommendation'][:80]}")


# ── CLI ─────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "check":
        config_file = sys.argv[2] if len(sys.argv) > 2 else None
        report = run_scan(config_file)
        print_report(report)
        # 保存报告
        report_file = f"percv-report-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n📄 报告已保存: {report_file}")

    elif cmd == "report":
        report_file = sys.argv[2] if len(sys.argv) > 2 else "percv-report.json"
        try:
            with open(report_file) as f:
                report = json.load(f)
            print_report(report)
        except FileNotFoundError:
            print(f"❌ 报告文件不存在: {report_file}")

    elif cmd == "init":
        output = sys.argv[2] if len(sys.argv) > 2 else "percv_config.json"
        initialize_config(output)

    elif cmd == "list-checks":
        print(f"\nPERCV 安全框架检查清单 ({len(PERCV_CHECKS)} 项):")
        for c in PERCV_CHECKS:
            sev = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            print(f"  {sev[c.severity]} [{c.check_id}] {c.name} ({c.category})")

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
