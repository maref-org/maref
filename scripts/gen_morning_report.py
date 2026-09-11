#!/usr/bin/env python3
"""晨报生成器 (Phase Beta B2) — 汇总所有治理报告产出"""
import json, os
from datetime import datetime, timezone
from pathlib import Path
from maref_config import REPORTS_DIR, vaccine_path

OUTPUT = REPORTS_DIR / f"morning-report-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def generate():
    report = {
        "report_id": f"MR-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": {},
    }

    # P-06 置信度
    conf = load_json(REPORTS_DIR / "confidence_audit.json")
    if conf:
        report["sections"]["confidence"] = {
            "value": conf.get("confidence_30d"),
            "legacy": 68,
            "calibrated": conf.get("calibrated"),
        }

    # P-01 翻案
    resample = load_json(REPORTS_DIR / "resample_log.json")
    if resample:
        report["sections"]["resample"] = {
            "sample_size": len(resample) if isinstance(resample, list) else 0,
        }

    # P-03 审批分层
    tier = load_json(REPORTS_DIR / "approval_tier_report.json")
    if tier:
        report["sections"]["approval_tier"] = {
            "total": tier.get("total_decisions"),
            "verdict": tier.get("verdict_distribution"),
            "risk": tier.get("risk_distribution"),
            "auto_approval": tier.get("auto_approval_feasibility"),
        }

    # P-04 僵死
    zombie = load_json(REPORTS_DIR / "zombie_agent_report.json")
    if zombie:
        report["sections"]["zombie_agents"] = {
            "count": zombie.get("zombie_count"),
        }

    # P-08 SLA
    sla = load_json(REPORTS_DIR / "backlog_sla_report.json")
    if sla:
        report["sections"]["sla"] = {
            "total_backlog": sla.get("total_backlog"),
            "high_risk": sla.get("high_risk_count"),
            "sla_met": sla.get("sla_met"),
        }

    # 审计健康
    audit_h = load_json(REPORTS_DIR / "audit_health_check.json")
    if audit_h:
        report["sections"]["audit_health"] = {
            "healthy": audit_h.get("healthy"),
            "issues": audit_h.get("issues"),
        }

    # 进化状态
    evo = load_json(REPORTS_DIR / "evolution_daemon_status.json")
    if evo:
        report["sections"]["evolution"] = {
            "healthy": evo.get("healthy"),
            "reason": evo.get("reason"),
        }

    # 疫苗计数
    vaccines = load_json(vaccine_path("vaccines.json"))
    if vaccines:
        report["sections"]["vaccines"] = {"total": len(vaccines) if isinstance(vaccines, list) else 0}

    # 总结
    issues = []
    if conf and conf.get("confidence_30d", 100) < 40:
        issues.append("置信度偏低")
    if audit_h and not audit_h.get("healthy"):
        issues.append("审计日志停滞")
    if evo and not evo.get("healthy"):
        issues.append("进化引擎停滞")
    if sla and sla.get("high_risk_count", 0) > 0:
        issues.append(f"高危积压 {sla.get('high_risk_count')} 条")
    if zombie and zombie.get("zombie_count", 0) > 5:
        issues.append(f"僵死 agent {zombie.get('zombie_count')} 个")

    report["summary"] = {
        "status": "healthy" if not issues else "attention",
        "issues": issues,
        "healthy_count": len(report["sections"]),
    }

    os.makedirs(OUTPUT.parent, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"晨报已生成: {OUTPUT}")
    print(f"状态: {report['summary']['status']}")
    if issues:
        print(f"⚠️ {len(issues)} 个需关注问题:")
        for i in issues:
            print(f"  - {i}")


if __name__ == "__main__":
    generate()