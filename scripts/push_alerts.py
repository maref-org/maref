#!/usr/bin/env python3
"""告警分级推送 (Phase Beta B4) — P-04 僵尸 + P-08 SLA → 通知"""
import json, os, urllib.request
from maref_config import REPORTS_DIR as REPORTS_DIR_P, RUNTIME_DIR, sidecar_url

REPORTS = str(REPORTS_DIR_P)
SIDECAR_URL = sidecar_url()
ALERTS_DIR = str(RUNTIME_DIR / ".openclaw" / "notifications")


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def push_alert(alert_type: str, message: str, severity: str):
    os.makedirs(ALERTS_DIR, exist_ok=True)
    timestamp = __import__("datetime").datetime.now().isoformat().replace(":", "-")
    alert_file = os.path.join(ALERTS_DIR, f"{timestamp}_{alert_type}_{severity}.json")
    with open(alert_file, "w") as f:
        json.dump({
            "type": alert_type,
            "severity": severity,
            "message": message,
            "timestamp": timestamp,
        }, f, indent=2)


def push_zombie_alerts():
    zombie = load_json(os.path.join(REPORTS, "zombie_agent_report.json"))
    if not zombie:
        return
    zombies = zombie.get("zombies", [])
    if not zombies:
        print("P-04: 无僵尸 Agent")
        return

    high_weight = [z for z in zombies if z.get("domain_weight", 1) >= 3]
    low_weight = [z for z in zombies if z.get("domain_weight", 1) < 3]

    if high_weight:
        names = ", ".join(z["agent"] for z in high_weight)
        push_alert("zombie_agents", f"域级告警: {names} 僵死, domain_weight>=3", "critical")

    if low_weight:
        names = ", ".join(z["agent"] for z in low_weight)
        push_alert("zombie_agents", f"提示: {names} 僵死", "warning")

    print(f"P-04 告警推送: {len(high_weight)} critical, {len(low_weight)} warning")


def push_sla_alerts():
    sla = load_json(os.path.join(REPORTS, "backlog_sla_report.json"))
    if not sla:
        return
    high = sla.get("high_risk_count", 0)
    if high > 0:
        push_alert("sla_violation", f"高危积压 {high} 条未清零", "critical")
        print(f"P-08 告警推送: {high} 条高危积压")
    else:
        print("P-08: SLA 达标")


def main():
    print("告警分级推送")
    print("=" * 40)
    push_zombie_alerts()
    push_sla_alerts()


if __name__ == "__main__":
    main()