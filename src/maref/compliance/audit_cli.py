#!/usr/bin/env python3
"""
MAS-TS Compliance Audit CLI — Agent 数据合规审计 CLI 工具

合规审计四阶段:
  1. Data Collection — 数据收集合规
  2. Data Processing — 数据处理合规
  3. Data Storage — 数据存储合规
  4. Data Deletion — 数据删除合规

适用法规: GDPR, PIPL (个人信息保护法), CCPA

用法:
    python3 scripts/compliance_audit_cli.py check <config.json>
    python3 scripts/compliance_audit_cli.py report <results.json>
    python3 scripts/compliance_audit_cli.py init [--output config.json]
    python3 scripts/compliance_audit_cli.py list-regulations
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] MAS-TS: %(message)s")
logger = logging.getLogger("mas_ts_compliance")

# ── 数据模型 ────────────────────────────────────────────────

@dataclass
class ComplianceCheck:
    check_id: str
    name: str
    phase: str          # collection | processing | storage | deletion
    regulation: str     # GDPR | PIPL | CCPA
    severity: str       # critical | high | medium | low
    status: str = "pending"  # pass | fail | warn | pending
    detail: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── 合规检查定义 ────────────────────────────────────────────

COMPLIANCE_CHECKS = [
    # ── Data Collection Phase ──
    ComplianceCheck("DC-01", "用户数据收集告知", "collection", "GDPR", "critical",
                    "是否明确告知用户收集了哪些数据",
                    "更新隐私政策，明确列出收集的数据类型和目的"),
    ComplianceCheck("DC-02", "用户明确同意", "collection", "GDPR", "critical",
                    "是否获得了用户的明确、自愿的同意",
                    "实施主动 opt-in 机制，禁用预勾选同意"),
    ComplianceCheck("DC-03", "数据最小化", "collection", "GDPR", "high",
                    "是否只收集业务必需的数据",
                    "审查数据收集清单，移除非必要字段"),
    ComplianceCheck("DC-04", "数据保留期限", "collection", "GDPR", "medium",
                    "是否有明确的数据保留和删除策略",
                    "制定数据保留期限表，实施自动过期删除"),
    ComplianceCheck("DC-05", "个人信息收集告知", "collection", "PIPL", "critical",
                    "是否告知个人信息的处理目的、方式和范围",
                    "在数据收集点显示《个人信息处理告知书》"),
    ComplianceCheck("DC-06", "单独同意", "collection", "PIPL", "high",
                    "敏感个人信息是否获得单独同意",
                    "对生物识别、行踪轨迹等敏感信息实施单独同意弹窗"),

    # ── Data Processing Phase ──
    ComplianceCheck("DP-01", "处理范围边界", "processing", "GDPR", "high",
                    "Agent 处理的数据范围是否有明确边界",
                    "定义 Agent 的数据处理范围声明，超出即告警"),
    ComplianceCheck("DP-02", "敏感数据脱敏", "processing", "GDPR", "critical",
                    "敏感数据在处理过程中是否脱敏",
                    "实施自动脱敏流水线: 检测→脱敏→审计"),
    ComplianceCheck("DP-03", "数据跨境传输", "processing", "GDPR", "high",
                    "数据跨境传输是否有合规依据",
                    "检查数据传输链路，确保有 SCC 或 BC 依据"),
    ComplianceCheck("DP-04", "训练数据合规", "processing", "PIPL", "critical",
                    "Agent 训练数据中是否包含个人信息",
                    "建立训练数据审查机制，去除可识别个人身份的信息"),
    ComplianceCheck("DP-05", "自动化决策说明", "processing", "PIPL", "medium",
                    "是否提供自动化决策的说明和拒绝权",
                    "在 Agent 交互界面显示决策依据说明"),

    # ── Data Storage Phase ──
    ComplianceCheck("DS-01", "数据存储区域合规", "storage", "GDPR", "high",
                    "数据是否存储在合规的地理区域",
                    "配置数据存储区域为 EU 或等效保护区域"),
    ComplianceCheck("DS-02", "加密存储", "storage", "GDPR", "critical",
                    "是否有加密存储措施",
                    "实施 AES-256 静态数据加密"),
    ComplianceCheck("DS-03", "访问控制机制", "storage", "GDPR", "high",
                    "是否有严格的访问控制机制",
                    "实施 RBAC + 审计日志，定期轮转凭据"),
    ComplianceCheck("DS-04", "数据备份恢复", "storage", "PIPL", "medium",
                    "是否有数据备份和灾难恢复计划",
                    "实施 3-2-1 备份策略，定期演练恢复"),

    # ── Data Deletion Phase ──
    ComplianceCheck("DD-01", "用户删除权", "deletion", "GDPR", "critical",
                    "用户是否可以要求删除其数据",
                    "实现用户数据删除接口，响应时间 < 30 天"),
    ComplianceCheck("DD-02", "关联删除机制", "deletion", "GDPR", "high",
                    "删除用户数据时是否级联删除关联数据",
                    "实现级联删除逻辑，确保不留数据残影"),
    ComplianceCheck("DD-03", "删除确认流程", "deletion", "GDPR", "medium",
                    "删除操作是否有确认和验证流程",
                    "删除前二次确认，删除后可验证"),

    # ── Cross-cutting ──
    ComplianceCheck("CC-01", "DPIA 数据保护影响评估", "collection", "GDPR", "high",
                    "高风险处理活动是否进行 DPIA",
                    "启动 DPIA 流程，记录风险评估结果"),
    ComplianceCheck("CC-02", "数据保护官任命", "processing", "GDPR", "medium",
                    "是否任命了数据保护官 (DPO)",
                    "指定 DPO 并公布联系方式"),
    ComplianceCheck("CC-03", "个人信息影响评估", "collection", "PIPL", "high",
                    "是否进行个人信息保护影响评估 (PIA)",
                    "完成 PIA 并保存评估报告至少 3 年"),
]


def build_config() -> dict:
    """生成 MAS-TS 合规配置骨架"""
    return {
        "framework": "MAS-TS",
        "version": "1.0.0",
        "regulations": ["GDPR", "PIPL", "CCPA"],
        "phases": ["collection", "processing", "storage", "deletion"],
        "checks": [c.to_dict() for c in COMPLIANCE_CHECKS],
    }


def initialize_config(output: str = "mas_ts_config.json") -> str:
    """生成 MAS-TS 配置文件"""
    config = build_config()
    path = output
    with open(path, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    logger.info("✅ MAS-TS 配置已生成: %s (%d 项检查)", path, len(COMPLIANCE_CHECKS))
    return path


def run_audit(config_file: str | None = None, regulations: list[str] | None = None) -> dict:
    """执行合规审计"""
    logger.info("🔍 MAS-TS 合规审计启动...")

    target_regs = regulations or ["GDPR", "PIPL"]
    checks = [c for c in COMPLIANCE_CHECKS if c.regulation in target_regs]
    if not checks:
        checks = COMPLIANCE_CHECKS

    results = []
    for check in checks:
        results.append({
            "check_id": check.check_id,
            "name": check.name,
            "phase": check.phase,
            "regulation": check.regulation,
            "severity": check.severity,
            "status": "pending",
            "detail": check.detail,
            "recommendation": check.recommendation,
        })

    # 按阶段分组统计
    phases = {}
    for r in results:
        phase = r["phase"]
        if phase not in phases:
            phases[phase] = {"total": 0, "passed": 0, "failed": 0, "warned": 0, "pending": 0}
        phases[phase]["total"] += 1
        phases[phase]["pending"] += 1

    report = {
        "auditor": "MAS-TS Compliance Audit CLI",
        "version": "1.0.0",
        "audit_id": f"mas-ts-audit-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "regulations": target_regs,
        "summary": {
            "total": len(results),
            "passed": 0,
            "failed": 0,
            "warned": 0,
            "pending": len(results),
            "compliance_score": 0.0,
            "phases": phases,
        },
        "checks": results,
    }

    # 合规评分
    severity_weights = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.3}
    total_weight = sum(severity_weights.get(c["severity"], 0.5) for c in results)
    pending_weight = sum(severity_weights.get(c["severity"], 0.5)
                        for c in results if c["status"] == "pending")
    report["summary"]["compliance_score"] = round(
        (1 - pending_weight / max(total_weight, 1)) * 100, 1
    ) if total_weight > 0 else 0.0

    logger.info("✅ 审计完成: %d 项检查, 合规评分: %.1f/100",
                report["summary"]["total"], report["summary"]["compliance_score"])
    return report


def print_report(report: dict):
    """打印人类可读的合规审计报告"""
    print(f"\n{'='*60}")
    print(f"  MAS-TS 数据合规审计报告")
    print(f"  ID: {report['audit_id']}")
    print(f"{'='*60}")
    print(f"  适用法规: {', '.join(report['regulations'])}")
    print(f"  审计时间: {report['audited_at'][:19]}")
    print(f"  合规评分: {report['summary']['compliance_score']}/100")
    print(f"  总检查项: {report['summary']['total']}")
    print(f"  ✅ 通过: {report['summary']['passed']}")
    print(f"  ❌ 失败: {report['summary']['failed']}")

    print(f"\n  各阶段概况:")
    phase_names = {"collection": "数据收集", "processing": "数据处理",
                   "storage": "数据存储", "deletion": "数据删除"}
    for phase, stats in report["summary"]["phases"].items():
        pname = phase_names.get(phase, phase)
        print(f"    {pname}: {stats['total']} 项 ({stats['pending']} 待定)")

    for check in report["checks"]:
        icon = {"pass": "✅", "fail": "❌", "warn": "⚠️", "pending": "⏳"}
        sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        print(f"\n  {icon[check['status']]} {sev_icon[check['severity']]} [{check['regulation']}] {check['check_id']}: {check['name']}")
        print(f"    阶段: {check['phase']}")
        print(f"    → {check['recommendation'][:80]}")


# ── CLI ─────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "check":
        config_file = sys.argv[2] if len(sys.argv) > 2 else None
        regs = sys.argv[3:] if len(sys.argv) > 3 else None
        report = run_audit(config_file, regs)
        print_report(report)
        report_file = f"mas-ts-audit-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n📄 报告已保存: {report_file}")

    elif cmd == "report":
        report_file = sys.argv[2] if len(sys.argv) > 2 else "mas-ts-audit.json"
        try:
            with open(report_file) as f:
                report = json.load(f)
            print_report(report)
        except FileNotFoundError:
            print(f"❌ 报告文件不存在: {report_file}")

    elif cmd == "init":
        output = sys.argv[2] if len(sys.argv) > 2 else "mas_ts_config.json"
        initialize_config(output)

    elif cmd == "list-regulations":
        print("MAS-TS 支持法规:")
        for r in ["GDPR", "PIPL", "CCPA"]:
            reg_checks = [c for c in COMPLIANCE_CHECKS if c.regulation == r]
            print(f"  {r}: {len(reg_checks)} 项检查")

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()