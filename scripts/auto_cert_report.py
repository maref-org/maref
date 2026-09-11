#!/usr/bin/env python3
"""自证报告自动化 + 增益复利追踪 (Phase Delta D3+D4)

D3: 每月自动生成治理自证报告，对比上月指标
D4: 跟踪飞轮增益率随时间的变化趋势
"""
import json, os
from datetime import datetime, timezone
from pathlib import Path
from maref_config import REPORTS_DIR

GAIN_LOG = REPORTS_DIR / "gain_compound_history.jsonl"


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def generate_cert_report():
    now = datetime.now(timezone.utc)
    conf = load_json(REPORTS_DIR / "confidence_audit.json")
    zombie = load_json(REPORTS_DIR / "zombie_agent_report.json")
    sla = load_json(REPORTS_DIR / "backlog_sla_report.json")
    tier = load_json(REPORTS_DIR / "approval_tier_report.json")
    gain_audit = load_json(REPORTS_DIR / "gain_audit_report.json")
    rq = load_json(REPORTS_DIR / "red_queen_validation.json")

    report = {
        "report_id": f"CERT-{now.strftime('%Y%m')}",
        "generated_at": now.isoformat(),
        "period": now.strftime("%Y-%m"),
        "indicators": {
            "confidence_30d": conf.get("confidence_30d") if conf else None,
            "confidence_calibrated": conf.get("calibrated") if conf else None,
            "zombie_agents": zombie.get("zombie_count") if zombie else None,
            "sla_backlog": sla.get("total_backlog") if sla else None,
            "sla_high_risk_cleared": sla.get("sla_met") if sla else None,
            "auto_approval_eligible": tier.get("auto_approval_feasibility") if tier else None,
            "gain_three_curves": bool(gain_audit) if gain_audit else None,
            "red_queen_pass_rate": rq.get("pass_rate") if rq else None,
        },
        "governance": {
            "decision_count": tier.get("total_decisions") if tier else None,
            "auto_approval_feasibility": tier.get("auto_approval_feasibility") if tier else None,
        },
        "status": "healthy",
    }

    issues = []
    if conf and conf.get("confidence_30d", 100) < 40:
        issues.append("置信度偏低")
    if zombie and zombie.get("zombie_count", 0) > 5:
        issues.append(f"僵死 agent 过多: {zombie.get('zombie_count')}")
    if sla and not sla.get("sla_met", True):
        issues.append("SLA 未达标")
    if rq and rq.get("pass_rate", 100) < 70:
        issues.append("红皇后校验未通过")

    if issues:
        report["status"] = "attention"
        report["issues"] = issues

    output = REPORTS_DIR / f"certification-{now.strftime('%Y%m')}.json"
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"自证报告: {output}")
    print(f"状态: {report['status']}")
    if issues:
        for i in issues:
            print(f"  ⚠️ {i}")
    return report


def track_gain_compound():
    conf = load_json(REPORTS_DIR / "confidence_audit.json")
    if not conf:
        print("无置信度数据，跳过高利追踪")
        return

    now = datetime.now(timezone.utc)
    current_gain = conf.get("confidence_30d", 68)

    history = []
    if GAIN_LOG.exists():
        with open(GAIN_LOG) as f:
            for line in f:
                try:
                    history.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass

    prev_gain = history[-1].get("confidence") if history else 68
    weekly_change = current_gain - prev_gain

    entry = {
        "timestamp": now.isoformat(),
        "week": now.strftime("%Y-W%W"),
        "confidence": current_gain,
        "weekly_change": round(weekly_change, 2),
        "compound_rate": round(current_gain / 68 - 1, 4) if history else 0,
        "weeks_tracked": len(history) + 1,
    }

    with open(GAIN_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"复利追踪: 周变化 {weekly_change:+.2f}, 累计 {entry['compound_rate']:+.4f}, 追踪 {entry['weeks_tracked']} 周")

    if len(history) >= 3:
        recent = [h["confidence"] for h in history[-3:]] + [current_gain]
        trend = "上升" if all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1)) else "下降" if all(recent[i] >= recent[i + 1] for i in range(len(recent) - 1)) else "波动"
        print(f"  四周趋势: {trend}")


def main():
    print("=" * 60)
    print("自证报告 + 复利追踪 (Phase Delta D3+D4)")
    print("=" * 60)
    print()
    generate_cert_report()
    print()
    track_gain_compound()


if __name__ == "__main__":
    main()